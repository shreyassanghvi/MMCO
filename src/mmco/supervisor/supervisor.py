"""The supervisor: spawn/monitor hosts, own shm, degrade gracefully, and auto-reconnect (spec §6).

The supervisor owns one runtime per sensor — ring (it is the sole shm owner), metadata queue,
control and log channels, a child host process, and a bus consumer — plus a shared ``Recorder``.
Each ``tick`` drains every consumer into the recorder, feeds the ``Watchdog``, and on a crash/hang
opens a coded gap, keeps the other streams recording, and re-spawns the dead host (re-binding by
stable identity) so it resumes into a new segment. ``stop`` tears everything down and ``unlink``s
every segment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from mmco.bus.bus import BusConsumer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer, sweep_stale_segments
from mmco.core.capabilities import Capabilities
from mmco.core.clock import MonotonicClock, OffsetRegistry
from mmco.core.logevent import LogEvent, LogLevel
from mmco.host.control import Control, LogChannel
from mmco.host.driver_host import HostSpec, spawn_driver_host
from mmco.record.recorder import Recorder
from mmco.supervisor.identity import IdentityRegistry
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.watchdog import Watchdog

_WATCHDOG_FACTOR = 20.0
_WATCHDOG_FLOOR_S = 1.0


@dataclass(frozen=True, slots=True)
class SensorSpec:
    """Per-sensor configuration the supervisor needs to run and re-bind a stream."""

    sensor_id: str
    identity: str
    rate_hz: float
    n_slots: int
    slot_size: int
    driver_factory: object
    driver_config: object
    capabilities: Capabilities


@dataclass
class _Runtime:
    spec: SensorSpec
    ring: RingBuffer
    metaqueue: MetaQueue
    control: Control
    log_channel: LogChannel
    consumer: BusConsumer
    process: object
    alive: bool = True
    attempts: int = 0
    next_respawn_at: float | None = None
    last_t_acquire_ns: int = field(default=0)


class Supervisor:
    """Orchestrates per-sensor hosts with health monitoring and auto-reconnect."""

    def __init__(
        self,
        *,
        session_id: str,
        base_dir: Path,
        specs: list[SensorSpec],
        policy: RestartPolicy,
    ):
        self._session_id = session_id
        self._base_dir = base_dir
        self._specs = specs
        self._policy = policy
        self._clock = MonotonicClock()
        self._watchdog = Watchdog()
        self._identity = IdentityRegistry()
        self._runtimes: dict[str, _Runtime] = {}
        self._recorder: Recorder | None = None
        self.aggregated_logs: list[LogEvent] = []
        self.respawns: dict[str, int] = {}

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        """Sweep stale segments, build per-sensor runtimes, and spawn every host."""
        sweep_stale_segments()
        anchor = self._clock.capture_anchor()
        self._recorder = Recorder(
            capabilities={s.sensor_id: s.capabilities for s in self._specs},
            offsets=OffsetRegistry(),
            session_id=self._session_id,
            base_dir=self._base_dir,
            anchor=anchor,
        )
        self._recorder.start()
        now = time.monotonic()
        for spec in self._specs:
            self._identity.register(spec.sensor_id, spec.identity)
            ring = RingBuffer.create(spec.n_slots, spec.slot_size)
            metaqueue = MetaQueue()
            control = Control()
            log_channel = LogChannel()
            consumer = BusConsumer(ring, metaqueue)
            self._watchdog.register(
                spec.sensor_id,
                rate_hz=spec.rate_hz,
                started_at=now,
                factor=_WATCHDOG_FACTOR,
                floor_s=_WATCHDOG_FLOOR_S,
            )
            process = self._spawn(spec, ring, metaqueue, control, log_channel)
            self._runtimes[spec.sensor_id] = _Runtime(
                spec=spec,
                ring=ring,
                metaqueue=metaqueue,
                control=control,
                log_channel=log_channel,
                consumer=consumer,
                process=process,
            )

    def _spawn(self, spec, ring, metaqueue, control, log_channel):
        host_spec = HostSpec(
            sensor_id=spec.sensor_id,
            rate_hz=spec.rate_hz,
            ring_name=ring.name,
            n_slots=spec.n_slots,
            slot_size=spec.slot_size,
            driver_factory=spec.driver_factory,
            driver_config=spec.driver_config,
        )
        return spawn_driver_host(host_spec, metaqueue, control, log_channel)

    # -- monitoring loop ----------------------------------------------------
    def tick(self) -> None:
        """One supervision pass: drain events/logs, then check + recover each stream."""
        now = time.monotonic()
        now_ns = self._clock.now_ns()
        for sensor_id, rt in self._runtimes.items():
            self._drain(rt, now)
            self.aggregated_logs.extend(rt.log_channel.drain(timeout=0.0))
            if rt.alive:
                self._check_health(sensor_id, rt, now, now_ns)
            elif rt.next_respawn_at is not None and now >= rt.next_respawn_at:
                self._respawn(sensor_id, rt, now)

    def _drain(self, rt: _Runtime, now: float) -> None:
        while True:
            result = rt.consumer.poll(timeout=0.0)
            if result is None:
                return
            meta, payload = result
            self._recorder.record(meta, payload)
            rt.last_t_acquire_ns = meta.t_acquire_ns
            self._watchdog.note_event(rt.spec.sensor_id, now)

    def _check_health(self, sensor_id: str, rt: _Runtime, now: float, now_ns: int) -> None:
        code = self._watchdog.check(sensor_id, now, rt.process.is_alive())
        if code is None:
            return
        rt.process.join(timeout=1.0)  # reap the dead child
        self._recorder.open_gap(
            sensor_id,
            start=rt.last_t_acquire_ns or now_ns,
            end=now_ns,
            reason=code.message,
            code=code,
        )
        self.aggregated_logs.append(
            LogEvent(t_ns=now_ns, level=LogLevel.ERROR, message=code.message,
                     code=code, sensor_id=sensor_id)
        )
        rt.alive = False
        rt.next_respawn_at = now + self._policy.backoff(rt.attempts)
        rt.attempts += 1

    def _respawn(self, sensor_id: str, rt: _Runtime, now: float) -> None:
        self._identity.resolve(rt.spec.identity)  # re-bind by stable identity, not index
        rt.process = self._spawn(
            rt.spec, rt.ring, rt.metaqueue, rt.control, rt.log_channel
        )
        rt.alive = True
        rt.next_respawn_at = None
        self._watchdog.note_event(sensor_id, now)  # grace so it is not instantly re-flagged
        self.respawns[sensor_id] = self.respawns.get(sensor_id, 0) + 1
        self.aggregated_logs.append(
            LogEvent(
                t_ns=self._clock.now_ns(),
                level=LogLevel.INFO,
                message=f"reconnect: re-spawned {sensor_id} by identity",
                sensor_id=sensor_id,
            )
        )

    def alive_sensors(self) -> list[str]:
        """Return sensor ids whose child process is still running."""
        return [sid for sid, rt in self._runtimes.items() if rt.process.is_alive()]

    def stop(self) -> Path:
        """Stop all hosts, drain the tail, write the manifest, and unlink every segment."""
        for rt in self._runtimes.values():
            rt.control.request_stop()
        for rt in self._runtimes.values():
            rt.process.join(timeout=3.0)
        now = time.monotonic()
        for sensor_id, rt in self._runtimes.items():
            self._drain(rt, now)  # tail events emitted before exit
            self.aggregated_logs.extend(rt.log_channel.drain(timeout=0.1))
            self._recorder.note_dropped(sensor_id, rt.consumer.dropped)
        manifest_file = self._recorder.stop()
        for rt in self._runtimes.values():
            rt.metaqueue.close()
            rt.log_channel.close()
            rt.ring.close()
            rt.ring.unlink()
        return manifest_file

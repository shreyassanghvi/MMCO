"""The driver host: a process wrapper running one sensor driver's acquisition loop (spec 3.1, 4.1).

The core creates the ring + queues, then spawns a child running :func:`run_driver_host`. The host
**attaches** the ring by name (never creates/unlinks it), then loops: read the driver, stamp
``t_acquire`` against its own monotonic clock, copy the payload into the ring via a ``BusProducer``,
and pace to the driver's nominal rate, checking the stop signal each iteration. Lifecycle and error
``LogEvent``s flow back on the log channel; a driver ``read()`` that raises becomes a
``DRIVER_CRASH`` log event and the host exits cleanly.

``spawn`` is the start method (Windows' default), so :func:`run_driver_host` and its arguments must
be importable and picklable — hence :class:`HostSpec` carries a picklable driver factory + config,
not a live driver instance.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from collections.abc import Callable
from dataclasses import dataclass

from mmco.bus.bus import BusProducer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.clock import MonotonicClock
from mmco.core.driver import DeviceDisconnectedError, SensorDriver
from mmco.core.errors import ErrorCode
from mmco.core.logevent import LogEvent, LogLevel
from mmco.host.control import Control, LogChannel


@dataclass(frozen=True, slots=True)
class HostSpec:
    """Everything needed to run one driver host, picklable for a spawned child."""

    sensor_id: str
    rate_hz: float
    ring_name: str
    n_slots: int
    slot_size: int
    driver_factory: Callable[..., SensorDriver]
    driver_config: object


def run_driver_host(
    spec: HostSpec,
    metaqueue: MetaQueue,
    control: Control,
    log_channel: LogChannel,
) -> None:
    """Acquisition loop for one driver; the spawn target run in a child process."""
    clock = MonotonicClock()
    ring = RingBuffer.attach(spec.ring_name, spec.n_slots, spec.slot_size)
    producer = BusProducer(ring, metaqueue)
    driver = spec.driver_factory(spec.driver_config)
    interval = 1.0 / spec.rate_hz if spec.rate_hz > 0 else 0.0
    seq = 0
    try:
        driver.open()
        log_channel.emit(
            LogEvent(
                t_ns=clock.now_ns(),
                level=LogLevel.INFO,
                message="driver opened",
                sensor_id=spec.sensor_id,
            )
        )
        while not control.stop_requested():
            try:
                sample = driver.read()
            except DeviceDisconnectedError as exc:  # clean device-gone -> E004
                log_channel.emit(
                    LogEvent(
                        t_ns=clock.now_ns(),
                        level=LogLevel.ERROR,
                        message=f"device disconnected: {exc}",
                        code=ErrorCode.DEVICE_DISCONNECTED,
                        sensor_id=spec.sensor_id,
                    )
                )
                break
            except Exception as exc:  # unexpected driver crash -> E002
                log_channel.emit(
                    LogEvent(
                        t_ns=clock.now_ns(),
                        level=LogLevel.ERROR,
                        message=f"driver read failed: {exc}",
                        code=ErrorCode.DRIVER_CRASH,
                        sensor_id=spec.sensor_id,
                    )
                )
                break
            producer.publish(
                sensor_id=spec.sensor_id,
                seq=seq,
                t_acquire_ns=clock.now_ns(),
                payload=sample.payload,
            )
            seq += 1
            if interval:
                time.sleep(interval)
    finally:
        try:
            driver.close()
        finally:
            log_channel.emit(
                LogEvent(
                    t_ns=clock.now_ns(),
                    level=LogLevel.INFO,
                    message="driver closed",
                    sensor_id=spec.sensor_id,
                )
            )
            ring.close()


def spawn_driver_host(
    spec: HostSpec,
    metaqueue: MetaQueue,
    control: Control,
    log_channel: LogChannel,
) -> mp.process.BaseProcess:
    """Start a driver host in a spawned child process and return the handle."""
    ctx = mp.get_context("spawn")
    proc = ctx.Process(
        target=run_driver_host,
        args=(spec, metaqueue, control, log_channel),
    )
    proc.start()
    return proc

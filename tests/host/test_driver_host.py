import struct
import time

from mmco.bus.bus import BusConsumer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.errors import ErrorCode
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.host.control import Control, LogChannel
from mmco.host.driver_host import HostSpec, spawn_driver_host

_N_SLOTS = 8
_SLOT_SIZE = 64


def _make_spec(ring: RingBuffer, failure: str | None = None) -> HostSpec:
    return HostSpec(
        sensor_id="sim0",
        rate_hz=50.0,
        ring_name=ring.name,
        n_slots=_N_SLOTS,
        slot_size=_SLOT_SIZE,
        driver_factory=SimulatedDriver,
        driver_config=SimConfig(
            sensor_id="sim0", rate_hz=50.0, failure=failure, failure_after=3
        ),
    )


def _collect(consumer: BusConsumer, n: int, timeout_s: float = 5.0) -> list:
    out: list = []
    deadline = time.monotonic() + timeout_s
    while len(out) < n and time.monotonic() < deadline:
        result = consumer.poll(timeout=0.5)
        if result is not None:
            out.append(result)
    return out


def test_host_delivers_stamped_events_and_lifecycle_logs_across_process_boundary():
    ring = RingBuffer.create(n_slots=_N_SLOTS, slot_size=_SLOT_SIZE)
    metaqueue = MetaQueue()
    control = Control()
    log_channel = LogChannel()
    proc = spawn_driver_host(_make_spec(ring), metaqueue, control, log_channel)
    consumer = BusConsumer(ring, metaqueue)
    try:
        collected = _collect(consumer, 5)
        assert len(collected) == 5

        timestamps = [meta.t_acquire_ns for meta, _ in collected]
        assert all(t > 0 for t in timestamps)
        assert timestamps == sorted(timestamps)  # non-decreasing
        values = [struct.unpack("<q", payload)[0] for _, payload in collected]
        assert values == [0, 1, 2, 3, 4]

        open_logs = log_channel.drain(timeout=1.0)
        assert any("open" in e.message for e in open_logs)
    finally:
        control.request_stop()
        proc.join(timeout=5.0)
        assert not proc.is_alive()
        close_logs = log_channel.drain(timeout=1.0)
        assert any("close" in e.message for e in close_logs)
        metaqueue.close()
        log_channel.close()
        ring.close()
        ring.unlink()


def test_driver_crash_surfaces_error_coded_log_and_child_exits():
    ring = RingBuffer.create(n_slots=_N_SLOTS, slot_size=_SLOT_SIZE)
    metaqueue = MetaQueue()
    control = Control()
    log_channel = LogChannel()
    proc = spawn_driver_host(_make_spec(ring, failure="crash"), metaqueue, control, log_channel)
    consumer = BusConsumer(ring, metaqueue)
    try:
        collected = _collect(consumer, 3)
        values = [struct.unpack("<q", payload)[0] for _, payload in collected]
        assert values == [0, 1, 2]  # the pre-crash events

        proc.join(timeout=5.0)  # child exits on its own after the crash
        assert not proc.is_alive()

        logs = log_channel.drain(timeout=1.0)
        assert any(e.code is ErrorCode.DRIVER_CRASH for e in logs)
    finally:
        control.request_stop()
        proc.join(timeout=5.0)
        metaqueue.close()
        log_channel.close()
        ring.close()
        ring.unlink()


def test_device_disconnect_surfaces_e004_log_and_child_exits():
    ring = RingBuffer.create(n_slots=_N_SLOTS, slot_size=_SLOT_SIZE)
    metaqueue = MetaQueue()
    control = Control()
    log_channel = LogChannel()
    proc = spawn_driver_host(
        _make_spec(ring, failure="disconnect"), metaqueue, control, log_channel
    )
    consumer = BusConsumer(ring, metaqueue)
    try:
        _collect(consumer, 3)  # the pre-disconnect events
        proc.join(timeout=5.0)
        assert not proc.is_alive()
        logs = log_channel.drain(timeout=1.0)
        assert any(e.code is ErrorCode.DEVICE_DISCONNECTED for e in logs)
    finally:
        control.request_stop()
        proc.join(timeout=5.0)
        metaqueue.close()
        log_channel.close()
        ring.close()
        ring.unlink()

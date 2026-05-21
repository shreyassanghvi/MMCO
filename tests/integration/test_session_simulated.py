"""End-to-end: a simulated driver host feeds the recorder, producing parquet + manifest.

This is the always-green CI backstop for the thin slice — no hardware, real process boundary.
(The ±2 ms cross-stream alignment check is deferred to Phase 9, which adds a real reference stream.)
"""

import time

import pyarrow.parquet as pq

from mmco.bus.bus import BusConsumer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor, OffsetRegistry
from mmco.core.manifest import SessionManifest
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.host.control import Control, LogChannel
from mmco.host.driver_host import HostSpec, spawn_driver_host
from mmco.paths import manifest_path, session_dir
from mmco.record.recorder import Recorder

_N_SLOTS = 16
_SLOT_SIZE = 64


def _sim_caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=50.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


def test_simulated_session_writes_parquet_and_manifest(tmp_path):
    ring = RingBuffer.create(n_slots=_N_SLOTS, slot_size=_SLOT_SIZE)
    metaqueue = MetaQueue()
    control = Control()
    log_channel = LogChannel()
    spec = HostSpec(
        sensor_id="sim0",
        rate_hz=50.0,
        ring_name=ring.name,
        n_slots=_N_SLOTS,
        slot_size=_SLOT_SIZE,
        driver_factory=SimulatedDriver,
        driver_config=SimConfig(sensor_id="sim0", rate_hz=50.0),
    )
    proc = spawn_driver_host(spec, metaqueue, control, log_channel)
    consumer = BusConsumer(ring, metaqueue)
    recorder = Recorder(
        consumer=consumer,
        capabilities={"sim0": _sim_caps()},
        offsets=OffsetRegistry(),
        session_id="sess-sim",
        base_dir=tmp_path,
        anchor=ClockAnchor(monotonic_ns=1, wall_ns=1_700_000_000_000_000_000),
    )
    try:
        recorder.start()
        recorded = 0
        deadline = time.monotonic() + 10.0
        while recorded < 10 and time.monotonic() < deadline:
            if recorder.record_available(timeout=0.5):
                recorded += 1
        assert recorded >= 10
    finally:
        control.request_stop()
        proc.join(timeout=5.0)
        recorder.stop()
        metaqueue.close()
        log_channel.close()
        ring.close()
        ring.unlink()

    sdir = session_dir(tmp_path, "sess-sim")
    assert manifest_path(sdir).exists()
    manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
    block = manifest.streams[0]
    assert block.sensor_id == "sim0"
    assert block.dropped == consumer.dropped  # bus drops surfaced (0 in a clean run)

    segment = block.segments[0]
    parquet_file = sdir / segment.file_path
    assert parquet_file.exists()
    t_events = pq.read_table(parquet_file).column("t_event").to_pylist()
    assert t_events == sorted(t_events)  # monotonic non-decreasing
    assert segment.start_timestamp == t_events[0]
    assert segment.end_timestamp == t_events[-1]

"""Cross-stream alignment via declared latency offsets (Task 9.3, spec §4.2/§9).

Two checks, both hardware-free and deterministic:
- a declared offset threads config -> SensorSpec -> OffsetRegistry -> the manifest block; and
- correcting a stream that is physically delayed by a constant latency brings it back into
  alignment with its reference **within ±2 ms**.
"""

from __future__ import annotations

import struct
import time

import pyarrow.parquet as pq

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor, OffsetRegistry
from mmco.core.events import EventMeta
from mmco.core.manifest import SessionManifest
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.paths import manifest_path, session_dir
from mmco.record.recorder import Recorder
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.supervisor import SensorSpec, Supervisor

_TOLERANCE_NS = 2_000_000  # ±2 ms


def _tabular_caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=50.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


def test_declared_offset_reaches_manifest_latency_offset(tmp_path):
    offset = 5_000_000  # 5 ms
    supervisor = Supervisor(
        session_id="sess-offset",
        base_dir=tmp_path,
        specs=[
            SensorSpec(
                sensor_id="imu0",
                identity="id-imu0",
                rate_hz=50.0,
                n_slots=16,
                slot_size=64,
                driver_factory=SimulatedDriver,
                driver_config=SimConfig(sensor_id="imu0", rate_hz=50.0),
                capabilities=_tabular_caps(),
                latency_offset_ns=offset,
            )
        ],
        policy=RestartPolicy(base_s=0.5, cap_s=5.0),
    )
    supervisor.start()
    try:
        for _ in range(10):
            supervisor.tick()
            time.sleep(0.02)
    finally:
        supervisor.stop()

    sdir = session_dir(tmp_path, "sess-offset")
    manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
    assert manifest.streams[0].latency_offset == offset


def test_offset_correction_aligns_delayed_stream_within_2ms(tmp_path):
    # Stream B observes the same events as A but is delayed by a constant latency L. Declaring
    # B's offset = L should bring its corrected timestamps back onto A's, well within ±2 ms.
    latency = 7_000_000  # 7 ms physical delay on B
    offsets = OffsetRegistry()
    offsets.set("ref", 0)
    offsets.set("delayed", latency)

    recorder = Recorder(
        capabilities={"ref": _tabular_caps(), "delayed": _tabular_caps()},
        offsets=offsets,
        session_id="sess-align",
        base_dir=tmp_path,
        anchor=ClockAnchor(monotonic_ns=0, wall_ns=1_700_000_000_000_000_000),
    )
    recorder.start()
    t0, step = 1_000_000_000, 20_000_000  # 50 Hz
    for i in range(10):
        t = t0 + i * step
        recorder.record(
            EventMeta(sensor_id="ref", seq=i, t_acquire_ns=t, slot=0, length=8, gen=i),
            struct.pack("<q", i),
        )
        recorder.record(
            EventMeta(
                sensor_id="delayed", seq=i, t_acquire_ns=t + latency, slot=0, length=8, gen=i
            ),
            struct.pack("<q", i),
        )
    recorder.stop()

    sdir = session_dir(tmp_path, "sess-align")
    manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
    by_id = {b.sensor_id: b for b in manifest.streams}
    ref_t = pq.read_table(sdir / by_id["ref"].segments[0].file_path).column("t_event").to_pylist()
    del_t = (
        pq.read_table(sdir / by_id["delayed"].segments[0].file_path)
        .column("t_event")
        .to_pylist()
    )
    assert len(ref_t) == len(del_t) == 10
    for a, b in zip(ref_t, del_t, strict=True):
        assert abs(a - b) <= _TOLERANCE_NS

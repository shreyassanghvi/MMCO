import struct

import pyarrow.parquet as pq

from mmco.bus.bus import BusConsumer, BusProducer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor, OffsetRegistry
from mmco.core.manifest import SessionManifest
from mmco.paths import manifest_path, session_dir
from mmco.record.recorder import Recorder


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=10.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


def test_recorder_writes_parquet_and_manifest(tmp_path):
    ring = RingBuffer.create(n_slots=8, slot_size=64)
    mq = MetaQueue()
    producer = BusProducer(ring, mq)
    consumer = BusConsumer(ring, mq)
    recorder = Recorder(
        consumer=consumer,
        capabilities={"imu0": _caps()},
        offsets=OffsetRegistry(),
        session_id="sess-001",
        base_dir=tmp_path,
        anchor=ClockAnchor(monotonic_ns=10, wall_ns=1_700_000_000_000_000_000),
    )
    try:
        recorder.start()
        for i in range(5):
            producer.publish(
                sensor_id="imu0", seq=i, t_acquire_ns=1_000 + i, payload=struct.pack("<q", i)
            )
        recorded = 0
        while recorded < 5:
            if recorder.record_available(timeout=0.2):
                recorded += 1
        recorder.stop()

        sdir = session_dir(tmp_path, "sess-001")
        assert manifest_path(sdir).exists()
        manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
        segment = manifest.streams[0].segments[0]
        parquet_file = sdir / segment.file_path
        assert parquet_file.exists()
        table = pq.read_table(parquet_file)
        assert table.num_rows == 5
        assert table.column("t_event").to_pylist() == [1_000, 1_001, 1_002, 1_003, 1_004]
    finally:
        mq.close()
        ring.close()
        ring.unlink()

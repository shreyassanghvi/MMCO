import struct

from mmco.bus.bus import BusConsumer, BusProducer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor, OffsetRegistry
from mmco.core.errors import ErrorCode
from mmco.core.manifest import SessionManifest
from mmco.paths import manifest_path, session_dir
from mmco.record.recorder import Recorder


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=10.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


def _drain(recorder: Recorder, n: int) -> None:
    got = 0
    while got < n:
        if recorder.record_available(timeout=0.2):
            got += 1


def test_gap_closes_segment_and_resume_opens_a_new_one(tmp_path):
    ring = RingBuffer.create(n_slots=8, slot_size=64)
    mq = MetaQueue()
    producer = BusProducer(ring, mq)
    consumer = BusConsumer(ring, mq)
    recorder = Recorder(
        consumer=consumer,
        capabilities={"imu0": _caps()},
        offsets=OffsetRegistry(),
        session_id="sess-gap",
        base_dir=tmp_path,
        anchor=ClockAnchor(monotonic_ns=1, wall_ns=1_700_000_000_000_000_000),
    )
    try:
        recorder.start()
        for i in range(2):  # segment 0
            producer.publish(
                sensor_id="imu0", seq=i, t_acquire_ns=1_000 + i, payload=struct.pack("<q", i)
            )
        _drain(recorder, 2)

        recorder.open_gap(
            "imu0", start=1_002, end=2_000, reason="driver crashed", code=ErrorCode.DRIVER_CRASH
        )

        for i in (2, 3):  # segment 1 (after resume)
            producer.publish(
                sensor_id="imu0", seq=i, t_acquire_ns=2_000 + i, payload=struct.pack("<q", i)
            )
        _drain(recorder, 2)
        recorder.stop()

        sdir = session_dir(tmp_path, "sess-gap")
        manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
        block = manifest.streams[0]
        assert [s.block_index for s in block.segments] == [0, 1]
        assert len(block.gaps) == 1
        assert block.gaps[0].code is ErrorCode.DRIVER_CRASH
        for segment in block.segments:
            assert (sdir / segment.file_path).exists()
        assert block.segments[0].end_timestamp <= block.gaps[0].start
        assert block.gaps[0].end <= block.segments[1].start_timestamp
    finally:
        mq.close()
        ring.close()
        ring.unlink()

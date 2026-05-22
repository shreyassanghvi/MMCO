import struct

import pytest

from mmco.bus.bus import BusConsumer, BusProducer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor, OffsetRegistry
from mmco.core.errors import ErrorCode
from mmco.core.manifest import SessionManifest
from mmco.paths import manifest_path, session_dir
from mmco.record import writer as writer_mod
from mmco.record.recorder import Recorder
from mmco.record.writer import StreamWriter, register_writer


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=10.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


class _FailingWriter(StreamWriter):
    def open(self) -> None:
        pass

    def write_event(self, t_event_ns: int, payload: bytes) -> None:
        raise RuntimeError("disk full")

    def close(self) -> None:
        pass


@pytest.fixture
def failing_writer_registered():
    saved = dict(writer_mod._REGISTRY)
    register_writer(StreamType.TABULAR, _FailingWriter)
    try:
        yield
    finally:
        writer_mod._REGISTRY.clear()
        writer_mod._REGISTRY.update(saved)


def test_writer_failure_becomes_e007_gap_without_crashing(tmp_path, failing_writer_registered):
    ring = RingBuffer.create(n_slots=8, slot_size=64)
    mq = MetaQueue()
    producer = BusProducer(ring, mq)
    consumer = BusConsumer(ring, mq)
    recorder = Recorder(
        consumer=consumer,
        capabilities={"imu0": _caps()},
        offsets=OffsetRegistry(),
        session_id="sess-wf",
        base_dir=tmp_path,
        anchor=ClockAnchor(monotonic_ns=1, wall_ns=1_700_000_000_000_000_000),
    )
    try:
        recorder.start()
        producer.publish(sensor_id="imu0", seq=0, t_acquire_ns=1_000, payload=struct.pack("<q", 0))
        # the write fails internally, but the recorder must not raise
        assert recorder.record_available(timeout=1.0) is True
        recorder.stop()

        sdir = session_dir(tmp_path, "sess-wf")
        manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
        block = manifest.streams[0]
        assert any(g.code is ErrorCode.WRITER_FAILURE for g in block.gaps)
    finally:
        mq.close()
        ring.close()
        ring.unlink()

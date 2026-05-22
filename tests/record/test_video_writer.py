"""Tests for the PyAV video writer + per-frame timestamp sidecar (Task 9.2)."""

from __future__ import annotations

import av
import pyarrow.parquet as pq

from mmco.core.capabilities import Capabilities, StreamType, VideoSchema
from mmco.core.clock import ClockAnchor, OffsetRegistry
from mmco.core.events import EventMeta
from mmco.core.manifest import SessionManifest
from mmco.paths import manifest_path, session_dir
from mmco.record.recorder import Recorder
from mmco.record.video_writer import VideoWriter, sidecar_path

_W, _H = 64, 48
_FRAME_BYTES = _W * _H * 3


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.VIDEO,
        rate=30.0,
        schema=VideoSchema(codec_or_raw="raw", width=_W, height=_H, pixel_format="rgb24"),
    )


def _frame(i: int) -> bytes:
    return bytes((i % 256,)) * _FRAME_BYTES


def _write_clip(path: str, *, n: int, profile=None, t0: int = 1_000):
    writer = VideoWriter(capabilities=_caps(), file_path=path, profile=profile)
    writer.open()
    t_events = [t0 + i * 33_000_000 for i in range(n)]
    for t, i in zip(t_events, range(n), strict=True):
        writer.write_event(t, _frame(i))
    writer.close()
    return writer, t_events


def test_encodes_expected_frame_count(tmp_path):
    path = str(tmp_path / "cam0.mp4")
    _write_clip(path, n=12)

    container = av.open(path)
    decoded = sum(1 for _ in container.decode(video=0))
    codec = container.streams.video[0].codec_context.name
    container.close()

    assert decoded == 12
    assert codec == "h264"


def test_sidecar_has_one_monotonic_t_event_per_frame(tmp_path):
    path = str(tmp_path / "cam0.mp4")
    _writer, t_events = _write_clip(path, n=8)

    table = pq.read_table(sidecar_path(path))
    recorded = table.column("t_event").to_pylist()

    assert recorded == t_events
    assert all(b > a for a, b in zip(recorded, recorded[1:], strict=False))


def test_tracks_start_and_end_timestamp(tmp_path):
    path = str(tmp_path / "cam0.mp4")
    writer, t_events = _write_clip(path, n=5)
    assert writer.start_timestamp == t_events[0]
    assert writer.end_timestamp == t_events[-1]


def test_profile_codec_is_honored(tmp_path):
    path = str(tmp_path / "cam0.mkv")
    _write_clip(path, n=4, profile={"container": "matroska", "codec": "libx264", "crf": 28})

    container = av.open(path)
    codec = container.streams.video[0].codec_context.name
    container.close()
    assert codec == "h264"


def test_recorder_writes_video_segment_into_manifest(tmp_path):
    recorder = Recorder(
        capabilities={"cam0": _caps()},
        offsets=OffsetRegistry(),
        session_id="sess-vid",
        base_dir=tmp_path,
        anchor=ClockAnchor(monotonic_ns=10, wall_ns=1_700_000_000_000_000_000),
        profiles={"cam0": {"container": "mp4", "codec": "libx264", "crf": 20}},
    )
    recorder.start()
    for i in range(6):
        meta = EventMeta(
            sensor_id="cam0", seq=i, t_acquire_ns=1_000 + i, slot=0, length=_FRAME_BYTES, gen=i
        )
        recorder.record(meta, _frame(i))
    recorder.stop()

    sdir = session_dir(tmp_path, "sess-vid")
    manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
    segment = manifest.streams[0].segments[0]
    assert segment.file_path.endswith(".mp4")
    assert (sdir / segment.file_path).exists()

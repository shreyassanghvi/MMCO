import json

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor
from mmco.core.errors import ErrorCode
from mmco.core.manifest import Gap, Segment, SessionManifest, StreamBlock


def _manifest() -> SessionManifest:
    caps = Capabilities(
        type=StreamType.TABULAR,
        rate=100.0,
        schema=TabularSchema(columns=(Column(name="ax", dtype="float32"),)),
    )
    block = StreamBlock(
        sensor_id="imu0",
        type=StreamType.TABULAR,
        capabilities=caps,
        latency_offset=250,
        dropped=False,
        segments=(
            Segment(
                file_path="imu0/000.parquet",
                start_timestamp=1_000,
                end_timestamp=2_000,
                block_index=0,
            ),
            Segment(
                file_path="imu0/001.parquet",
                start_timestamp=3_000,
                end_timestamp=4_000,
                block_index=1,
            ),
        ),
        gaps=(
            Gap(
                start=2_000,
                end=3_000,
                reason="cable unplugged",
                code=ErrorCode.DEVICE_DISCONNECTED,
            ),
        ),
    )
    return SessionManifest(
        session_id="sess-001",
        anchor=ClockAnchor(monotonic_ns=10, wall_ns=1_700_000_000_000_000_000),
        output_dir="recordings/sess-001",
        streams=(block,),
    )


def test_manifest_round_trips_through_json():
    manifest = _manifest()
    assert SessionManifest.from_json(manifest.to_json()) == manifest


def test_segment_and_gap_order_is_preserved():
    manifest = SessionManifest.from_json(_manifest().to_json())
    block = manifest.streams[0]
    assert [s.block_index for s in block.segments] == [0, 1]
    assert block.gaps[0].reason == "cable unplugged"


def test_serialized_shape_uses_stable_keys_and_error_code_string():
    data = json.loads(_manifest().to_json())
    assert set(data) == {"session_id", "anchor", "output_dir", "streams"}
    stream = data["streams"][0]
    assert set(stream) == {
        "sensor_id",
        "type",
        "capabilities",
        "latency_offset",
        "dropped",
        "segments",
        "gaps",
    }
    # gap code serializes to its stable string and round-trips back to the enum
    assert stream["gaps"][0]["code"] == "MMCO-E004"
    restored = SessionManifest.from_json(_manifest().to_json())
    assert restored.streams[0].gaps[0].code is ErrorCode.DEVICE_DISCONNECTED

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor
from mmco.core.manifest import Segment, SessionManifest
from mmco.record.manifest_author import ManifestAuthor


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=10.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


def test_author_writes_round_trippable_manifest(tmp_path):
    anchor = ClockAnchor(monotonic_ns=10, wall_ns=1_700_000_000_000_000_000)
    author = ManifestAuthor(
        session_id="sess-001", output_dir="recordings/sess-001", anchor=anchor
    )
    author.add_stream("imu0", StreamType.TABULAR, _caps(), latency_offset=250)
    segment = Segment(
        file_path="imu0/000.parquet",
        start_timestamp=1_000,
        end_timestamp=2_000,
        block_index=0,
    )
    author.add_segment("imu0", segment)
    author.set_dropped("imu0", 3)

    path = tmp_path / "manifest.json"
    author.write(str(path))

    manifest = SessionManifest.from_json(path.read_text())
    assert manifest.session_id == "sess-001"
    block = manifest.streams[0]
    assert block.sensor_id == "imu0"
    assert block.latency_offset == 250
    assert block.dropped == 3
    assert block.segments == (segment,)
    assert block.segments[0].start_timestamp <= block.segments[0].end_timestamp

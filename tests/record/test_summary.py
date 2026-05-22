from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.clock import ClockAnchor
from mmco.core.errors import ErrorCode
from mmco.core.logevent import LogEvent, LogLevel
from mmco.core.manifest import Gap, Segment, SessionManifest, StreamBlock
from mmco.paths import MANIFEST_FILENAME, SESSION_LOG_FILENAME, SUMMARY_FILENAME
from mmco.record.session_log import write_log
from mmco.record.summary import render_summary, write_summary


def _manifest() -> SessionManifest:
    caps = Capabilities(
        type=StreamType.TABULAR,
        rate=50.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )
    block = StreamBlock(
        sensor_id="sim0",
        type=StreamType.TABULAR,
        capabilities=caps,
        latency_offset=0,
        dropped=0,
        segments=(
            Segment(
                file_path="sim0-000.parquet",
                start_timestamp=1_000_000_000,
                end_timestamp=2_000_000_000,
                block_index=0,
            ),
        ),
        gaps=(
            Gap(
                start=2_000_000_000,
                end=3_000_000_000,
                reason="cable unplugged",
                code=ErrorCode.DEVICE_DISCONNECTED,
            ),
        ),
    )
    return SessionManifest(
        session_id="sess-doc",
        anchor=ClockAnchor(monotonic_ns=10, wall_ns=1_700_000_000_000_000_000),
        output_dir="recordings/sess-doc",
        streams=(block,),
    )


def _events() -> list[LogEvent]:
    return [
        LogEvent(
            t_ns=2_000_000_000,
            level=LogLevel.ERROR,
            message="device disconnected",
            code=ErrorCode.DEVICE_DISCONNECTED,
            sensor_id="sim0",
        ),
    ]


def test_render_summary_describes_streams_and_faults():
    text = render_summary(_manifest(), _events())
    assert "sess-doc" in text
    assert "sim0" in text
    assert "MMCO-E004" in text  # the code
    assert "device disconnected" in text  # plain-English message
    assert "1" in text  # one segment


def test_write_summary_reads_artifacts_and_writes_summary_md(tmp_path):
    session_dir = tmp_path / "recordings" / "sess-doc"
    session_dir.mkdir(parents=True)
    (session_dir / MANIFEST_FILENAME).write_text(_manifest().to_json())
    write_log(str(session_dir / SESSION_LOG_FILENAME), _events())

    out = write_summary(session_dir)

    assert out == session_dir / SUMMARY_FILENAME
    text = out.read_text()
    assert text.strip()  # non-empty
    assert "sim0" in text
    assert "MMCO-E004" in text

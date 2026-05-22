from mmco.core.errors import ErrorCode
from mmco.core.logevent import LogEvent, LogLevel
from mmco.record.session_log import read_log, write_log


def _events() -> list[LogEvent]:
    return [
        LogEvent(t_ns=1, level=LogLevel.INFO, message="driver opened", sensor_id="sim0"),
        LogEvent(
            t_ns=2,
            level=LogLevel.ERROR,
            message="device disconnected",
            code=ErrorCode.DEVICE_DISCONNECTED,
            sensor_id="sim0",
        ),
        LogEvent(t_ns=3, level=LogLevel.INFO, message="reconnect", sensor_id="sim0"),
    ]


def test_write_then_read_round_trips_in_order(tmp_path):
    path = tmp_path / "session.log.jsonl"
    events = _events()
    write_log(str(path), events)
    assert read_log(str(path)) == events


def test_one_json_line_per_event(tmp_path):
    path = tmp_path / "session.log.jsonl"
    write_log(str(path), _events())
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 3


def test_code_survives_round_trip(tmp_path):
    path = tmp_path / "session.log.jsonl"
    write_log(str(path), _events())
    restored = read_log(str(path))
    assert restored[1].code is ErrorCode.DEVICE_DISCONNECTED

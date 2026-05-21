import json

from mmco.core.errors import ErrorCode
from mmco.core.logevent import LogEvent, LogLevel


def test_log_event_round_trips_through_jsonl_including_extra():
    event = LogEvent(
        t_ns=1_234,
        level=LogLevel.INFO,
        message="capture started",
        sensor_id="cam0",
        extra={"fps": 30, "profile": "v4l2"},
    )
    line = event.to_json()
    assert "\n" not in line  # one JSONL record per line
    assert LogEvent.from_json(line) == event


def test_code_serializes_to_stable_string_and_absent_code_is_null():
    with_code = LogEvent(
        t_ns=1,
        level=LogLevel.ERROR,
        message="driver crashed",
        code=ErrorCode.DRIVER_CRASH,
    )
    data = json.loads(with_code.to_json())
    assert data["code"] == "MMCO-E002"
    assert LogEvent.from_json(with_code.to_json()).code is ErrorCode.DRIVER_CRASH

    without_code = LogEvent(t_ns=2, level=LogLevel.DEBUG, message="tick")
    assert json.loads(without_code.to_json())["code"] is None
    assert LogEvent.from_json(without_code.to_json()).code is None


def test_log_level_ordering_supports_threshold_filtering():
    assert LogLevel.DEBUG < LogLevel.INFO < LogLevel.WARNING < LogLevel.ERROR
    events = [
        LogEvent(t_ns=1, level=LogLevel.DEBUG, message="d"),
        LogEvent(t_ns=2, level=LogLevel.WARNING, message="w"),
        LogEvent(t_ns=3, level=LogLevel.ERROR, message="e"),
    ]
    at_least_warning = [e for e in events if e.level >= LogLevel.WARNING]
    assert [e.message for e in at_least_warning] == ["w", "e"]

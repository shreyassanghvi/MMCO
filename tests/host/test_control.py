from mmco.core.errors import ErrorCode
from mmco.core.logevent import LogEvent, LogLevel
from mmco.host.control import Control, LogChannel


def test_control_starts_unset_and_flips_on_request_stop():
    control = Control()
    assert control.stop_requested() is False
    control.request_stop()
    assert control.stop_requested() is True


def test_log_channel_round_trips_event_including_code():
    channel = LogChannel()
    try:
        event = LogEvent(
            t_ns=1,
            level=LogLevel.ERROR,
            message="driver crashed",
            code=ErrorCode.DRIVER_CRASH,
            sensor_id="sim0",
        )
        assert channel.emit(event) is True
        drained = channel.drain(timeout=1.0)
        assert drained == [event]
    finally:
        channel.close()


def test_drain_on_empty_returns_empty_list():
    channel = LogChannel()
    try:
        assert channel.drain(timeout=0.05) == []
    finally:
        channel.close()


def test_drain_returns_events_in_fifo_order():
    channel = LogChannel()
    try:
        for i in range(3):
            channel.emit(LogEvent(t_ns=i, level=LogLevel.INFO, message=f"m{i}"))
        drained = channel.drain(timeout=1.0)
        assert [e.message for e in drained] == ["m0", "m1", "m2"]
    finally:
        channel.close()

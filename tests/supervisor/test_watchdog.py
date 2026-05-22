from mmco.core.errors import ErrorCode
from mmco.supervisor.watchdog import Watchdog


def _watchdog() -> Watchdog:
    wd = Watchdog()
    # rate 50 Hz, factor 5 -> timeout max(5/50, 0.05) = 0.1 s
    wd.register("imu0", rate_hz=50.0, started_at=0.0, factor=5.0, floor_s=0.05)
    return wd


def test_dead_process_is_a_crash():
    wd = _watchdog()
    assert wd.check("imu0", now=0.01, alive=False) is ErrorCode.DRIVER_CRASH


def test_no_events_past_timeout_is_a_hang():
    wd = _watchdog()
    wd.note_event("imu0", now=0.0)
    assert wd.check("imu0", now=0.2, alive=True) is ErrorCode.WATCHDOG_TIMEOUT


def test_slow_but_alive_stream_is_not_killed():
    wd = _watchdog()
    # events keep arriving within the timeout window -> healthy
    wd.note_event("imu0", now=0.0)
    wd.note_event("imu0", now=0.08)
    assert wd.check("imu0", now=0.09, alive=True) is None


def test_note_event_resets_the_timeout_clock():
    wd = _watchdog()
    wd.note_event("imu0", now=0.0)
    assert wd.check("imu0", now=0.15, alive=True) is ErrorCode.WATCHDOG_TIMEOUT
    wd.note_event("imu0", now=0.15)
    assert wd.check("imu0", now=0.2, alive=True) is None

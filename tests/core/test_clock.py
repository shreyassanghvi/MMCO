from mmco.core.clock import ClockAnchor, MonotonicClock, OffsetRegistry


def test_unknown_sensor_offset_defaults_to_zero():
    reg = OffsetRegistry()
    assert reg.get("cam0") == 0
    # t_event == t_acquire when no offset is registered
    assert reg.event_time("cam0", 1_000) == 1_000


def test_event_time_subtracts_registered_offset():
    reg = OffsetRegistry()
    reg.set("imu0", 250)
    assert reg.get("imu0") == 250
    assert reg.event_time("imu0", 1_000) == 750  # t_event = t_acquire - offset


def test_capture_anchor_returns_int_monotonic_and_wall_pair():
    clock = MonotonicClock()
    anchor = clock.capture_anchor()
    assert isinstance(anchor, ClockAnchor)
    assert isinstance(anchor.monotonic_ns, int)
    assert isinstance(anchor.wall_ns, int)


def test_now_ns_is_non_decreasing():
    clock = MonotonicClock()
    first = clock.now_ns()
    second = clock.now_ns()
    assert isinstance(first, int)
    assert second >= first

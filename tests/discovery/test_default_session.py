"""Tests for the default-session builder (Tasks 8.2 + 8.3)."""

from __future__ import annotations

from mmco.config.config import SessionConfig
from mmco.discovery.default_session import build_default_session
from mmco.discovery.discovery import DeviceKind, DiscoveredDevice

_VIDEO = DiscoveredDevice(
    kind=DeviceKind.VIDEO, node="/dev/video0", identity="usb-c920-video", description="C920"
)
_SERIAL = DiscoveredDevice(
    kind=DeviceKind.SERIAL, node="/dev/ttyUSB0", identity="usb-arduino", description="IMU"
)


def test_builder_maps_devices_to_sensors_when_drivers_runnable():
    config = build_default_session(
        [_VIDEO, _SERIAL],
        output_dir="out",
        runnable_drivers={"webcam_v4l2", "serial_imu"},
    )

    assert isinstance(config, SessionConfig)
    assert config.output_dir == "out"
    by_driver = {s.driver: s for s in config.sensors}
    assert by_driver["webcam_v4l2"].identity == "usb-c920-video"
    assert by_driver["serial_imu"].identity == "usb-arduino"
    assert len({s.id for s in config.sensors}) == 2  # distinct ids


def test_builder_filters_out_devices_without_a_runnable_driver():
    # Today's real registry only runs "simulated": real devices are reported by discovery but
    # produce no runnable real sensor (the honest Phase 8 seam).
    config = build_default_session(
        [_VIDEO, _SERIAL], output_dir="out", runnable_drivers={"simulated"}
    )
    real = [s for s in config.sensors if s.driver in {"webcam_v4l2", "serial_imu"}]
    assert real == []


def test_builder_falls_back_to_simulated_when_nothing_runnable():
    # No devices at all → a fresh clone still records via the simulated sensor.
    empty = build_default_session([], output_dir="out", runnable_drivers={"simulated"})
    assert len(empty.sensors) == 1
    assert empty.sensors[0].driver == "simulated"
    assert empty.sensors[0].rate_hz > 0

    # Real devices found but none runnable → real ones filtered, simulated fallback applied.
    filtered = build_default_session(
        [_VIDEO, _SERIAL], output_dir="out", runnable_drivers={"simulated"}
    )
    assert [s.driver for s in filtered.sensors] == ["simulated"]


def test_builder_does_not_add_simulated_when_a_real_driver_runs():
    config = build_default_session(
        [_VIDEO], output_dir="out", runnable_drivers={"webcam_v4l2"}
    )
    assert [s.driver for s in config.sensors] == ["webcam_v4l2"]

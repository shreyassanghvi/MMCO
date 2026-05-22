"""Tests for the V4L2 webcam driver against its fake-capture seam (Task 9.1)."""

from __future__ import annotations

import pytest

from mmco.core.capabilities import StreamType, VideoSchema
from mmco.core.driver import DeviceDisconnectedError, DriverHealth
from mmco.drivers.webcam_v4l2 import WebcamConfig, WebcamDriver

_W, _H = 64, 48
_FRAME_BYTES = _W * _H * 3  # rgb24


def _fake_config(**overrides) -> WebcamConfig:
    base = dict(
        sensor_id="cam0",
        identity="usb-c920-video",
        width=_W,
        height=_H,
        fps=30.0,
        backend="fake",
        fake_nodes=("/dev/video0",),
    )
    base.update(overrides)
    return WebcamConfig(**base)


def test_open_read_yields_frame_bytes_and_video_schema():
    driver = WebcamDriver(_fake_config())
    driver.open()
    sample = driver.read()
    driver.close()

    assert len(sample.payload) == _FRAME_BYTES
    assert sample.payload_schema_ref  # non-empty schema ref


def test_capabilities_report_video_at_configured_geometry():
    driver = WebcamDriver(_fake_config())
    caps = driver.capabilities
    assert caps.type is StreamType.VIDEO
    assert caps.rate == 30.0
    assert isinstance(caps.schema, VideoSchema)
    assert (caps.schema.width, caps.schema.height) == (_W, _H)
    assert driver.health() is DriverHealth.OK


def test_read_after_disconnect_after_raises_device_disconnected():
    driver = WebcamDriver(_fake_config(disconnect_after=2))
    driver.open()
    driver.read()
    driver.read()
    with pytest.raises(DeviceDisconnectedError):
        driver.read()
    driver.close()


def test_reconnect_resolves_to_a_different_node_by_identity():
    # Same identity, but the device re-enumerates at a new index on re-open.
    driver = WebcamDriver(_fake_config(fake_nodes=("/dev/video0", "/dev/video2")))
    driver.open()
    assert driver.node == "/dev/video0"
    driver.read()
    driver.close()

    driver.open()  # re-open → identity resolves to the new index
    assert driver.node == "/dev/video2"
    assert len(driver.read().payload) == _FRAME_BYTES
    driver.close()

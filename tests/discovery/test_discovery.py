"""Tests for device discovery behind injectable enumerators (Task 8.1)."""

from __future__ import annotations

from mmco.discovery.discovery import DeviceKind, DiscoveredDevice, discover_devices


def _fake_video():
    return [
        DiscoveredDevice(
            kind=DeviceKind.VIDEO,
            node="/dev/video0",
            identity="usb-046d_HD_Pro_Webcam_C920-video-index0",
            description="HD Pro Webcam C920",
        )
    ]


def _fake_serial():
    return [
        DiscoveredDevice(
            kind=DeviceKind.SERIAL,
            node="/dev/ttyUSB0",
            identity="usb-Arduino_LLC_ttyUSB0",
            description="Arduino IMU",
        )
    ]


def test_discover_devices_flattens_enumerators_with_stable_identity():
    devices = discover_devices(enumerators=[_fake_serial, _fake_video])

    assert len(devices) == 2
    kinds = [d.kind for d in devices]
    assert DeviceKind.VIDEO in kinds and DeviceKind.SERIAL in kinds

    video = next(d for d in devices if d.kind is DeviceKind.VIDEO)
    assert video.node == "/dev/video0"
    # the stable identity, not the transient node, is what reconnect binds to
    assert video.identity == "usb-046d_HD_Pro_Webcam_C920-video-index0"
    assert video.identity != video.node


def test_discover_devices_is_deterministically_ordered():
    forward = discover_devices(enumerators=[_fake_video, _fake_serial])
    reversed_ = discover_devices(enumerators=[_fake_serial, _fake_video])
    assert forward == reversed_  # order independent of enumerator order


def test_discover_devices_empty_when_no_devices():
    assert discover_devices(enumerators=[]) == []
    assert discover_devices(enumerators=[lambda: []]) == []

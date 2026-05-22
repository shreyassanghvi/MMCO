import pytest

from mmco.supervisor.identity import IdentityRegistry


def test_resolve_returns_registered_sensor():
    reg = IdentityRegistry()
    reg.register("imu0", "usb-046d_C920-serialABC")
    assert reg.resolve("usb-046d_C920-serialABC") == "imu0"


def test_same_identity_resolves_regardless_of_device_index():
    reg = IdentityRegistry()
    reg.register("cam0", "usb-046d_C920-serialABC")
    # The device may re-enumerate at a different /dev index; resolution is by identity only.
    assert reg.resolve("usb-046d_C920-serialABC") == "cam0"  # was index 0
    assert reg.resolve("usb-046d_C920-serialABC") == "cam0"  # now index 3, same identity


def test_unknown_identity_raises():
    reg = IdentityRegistry()
    with pytest.raises(KeyError):
        reg.resolve("not-registered")

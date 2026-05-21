import pytest

from mmco.core.errors import ErrorCode


def test_all_codes_are_unique_with_non_empty_messages():
    codes = [member.code for member in ErrorCode]
    assert len(codes) == len(set(codes))
    assert all(member.message for member in ErrorCode)


def test_from_code_looks_up_member_and_rejects_unknown():
    assert ErrorCode.from_code("MMCO-E003") is ErrorCode.WATCHDOG_TIMEOUT
    with pytest.raises(ValueError):
        ErrorCode.from_code("MMCO-E999")


def test_code_strings_are_stable_literals():
    assert ErrorCode.DEVICE_NOT_FOUND.code == "MMCO-E001"
    assert ErrorCode.DRIVER_CRASH.code == "MMCO-E002"
    assert ErrorCode.WATCHDOG_TIMEOUT.code == "MMCO-E003"
    assert ErrorCode.DEVICE_DISCONNECTED.code == "MMCO-E004"
    assert ErrorCode.SHM_BUFFER_FULL.code == "MMCO-E005"
    assert ErrorCode.CONFIG_INVALID.code == "MMCO-E006"
    assert ErrorCode.WRITER_FAILURE.code == "MMCO-E007"
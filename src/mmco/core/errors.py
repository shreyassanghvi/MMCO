"""The MMCO error-code taxonomy (design spec §6).

Every failure the system can surface has a stable, generic code (``MMCO-Exxx``) and a default
human-readable message. Codes are written into the session log and the manifest's gap records, so a
scientist reading a summary sees *what* failed (device gone, driver crash, watchdog timeout, ...)
without reading code. The code strings are part of the contract — keep them stable.
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(Enum):
    """A stable failure code paired with a default human message."""

    DEVICE_NOT_FOUND = ("MMCO-E001", "device not found")
    DRIVER_CRASH = ("MMCO-E002", "driver crashed")
    WATCHDOG_TIMEOUT = ("MMCO-E003", "watchdog timeout")
    DEVICE_DISCONNECTED = ("MMCO-E004", "device disconnected")
    SHM_BUFFER_FULL = ("MMCO-E005", "shared-memory buffer full")
    CONFIG_INVALID = ("MMCO-E006", "configuration invalid")
    WRITER_FAILURE = ("MMCO-E007", "writer failure")

    def __init__(self, code: str, message: str) -> None:
        self._code = code
        self._message = message

    @property
    def code(self) -> str:
        """The stable ``MMCO-Exxx`` code string."""
        return self._code

    @property
    def message(self) -> str:
        """The default human-readable message."""
        return self._message

    @classmethod
    def from_code(cls, code: str) -> ErrorCode:
        """Look up a member by its code string; raise ``ValueError`` if unknown."""
        for member in cls:
            if member.code == code:
                return member
        raise ValueError(f"unknown error code: {code!r}")

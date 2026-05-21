"""The structured log-event model (design spec §6).

Every component — drivers, host, recorder, supervisor — emits the same :class:`LogEvent` shape, one
JSON object per line (JSONL). An optional :class:`~mmco.core.errors.ErrorCode` ties a message to a
generic failure code so the auto-generated summary can explain *what* went wrong. :class:`LogLevel`
is ordered so consumers can filter at or above a threshold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum

from mmco.core.errors import ErrorCode


class LogLevel(IntEnum):
    """Ordered severity levels (higher is more severe)."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


@dataclass(frozen=True, slots=True)
class LogEvent:
    """A single structured log record shared by every component."""

    t_ns: int
    level: LogLevel
    message: str
    code: ErrorCode | None = None
    sensor_id: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "t_ns": self.t_ns,
            "level": self.level.name,
            "message": self.message,
            "code": self.code.code if self.code is not None else None,
            "sensor_id": self.sensor_id,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LogEvent:
        raw_code = data.get("code")
        return cls(
            t_ns=data["t_ns"],
            level=LogLevel[data["level"]],
            message=data["message"],
            code=ErrorCode.from_code(raw_code) if raw_code is not None else None,
            sensor_id=data.get("sensor_id"),
            extra=data.get("extra") or {},
        )

    def to_json(self) -> str:
        """Serialize to a single-line JSONL record."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, line: str) -> LogEvent:
        return cls.from_dict(json.loads(line))

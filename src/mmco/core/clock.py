"""Monotonic timing and the latency-offset registry (design spec §4.2).

All per-event stamps come from one monotonic source (:class:`MonotonicClock`), so cross-stream
alignment never depends on wall-clock adjustments. A single :class:`ClockAnchor` captured at session
start pairs that monotonic reading with ``CLOCK_REALTIME`` to place the session on absolute time
without polluting per-event stamps.

The :class:`OffsetRegistry` holds each sensor's measured driver+buffer latency. The corrected event
time is ``t_event = t_acquire - offset``; an unregistered sensor defaults to a zero offset (raw
acquisition time).
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClockAnchor:
    """A single paired reading of the monotonic and wall clocks, in nanoseconds."""

    monotonic_ns: int
    wall_ns: int


class MonotonicClock:
    """Thin wrapper over the process monotonic clock."""

    def now_ns(self) -> int:
        """Return the current monotonic time in nanoseconds (non-decreasing)."""
        return time.monotonic_ns()

    def capture_anchor(self) -> ClockAnchor:
        """Capture a monotonic↔wall pair for absolute-time mapping."""
        return ClockAnchor(monotonic_ns=time.monotonic_ns(), wall_ns=time.time_ns())


class OffsetRegistry:
    """Maps ``sensor_id`` to its latency offset (ns) and corrects acquisition times."""

    def __init__(self) -> None:
        self._offsets: dict[str, int] = {}

    def set(self, sensor_id: str, offset_ns: int) -> None:
        """Register ``sensor_id``'s latency offset in nanoseconds."""
        self._offsets[sensor_id] = offset_ns

    def get(self, sensor_id: str) -> int:
        """Return ``sensor_id``'s offset, or ``0`` if none is registered."""
        return self._offsets.get(sensor_id, 0)

    def event_time(self, sensor_id: str, t_acquire_ns: int) -> int:
        """Return ``t_event = t_acquire - offset`` for ``sensor_id``."""
        return t_acquire_ns - self.get(sensor_id)

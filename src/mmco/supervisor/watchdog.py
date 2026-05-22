"""Per-stream health detection (design spec §6).

The watchdog turns liveness signals into error codes: a host that has exited is a crash
(``E002``); a host that is alive but has gone silent past its per-stream timeout is a hang
(``E003``). The timeout is derived from the declared rate — ``max(factor / rate_hz, floor_s)`` — so
a legitimately slow-but-alive stream that keeps emitting is never falsely killed.

All checks take an explicit monotonic ``now`` so the supervisor controls the clock and tests are
deterministic without sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass

from mmco.core.errors import ErrorCode


@dataclass
class _StreamHealth:
    timeout_s: float
    last_event: float


class Watchdog:
    """Tracks per-stream last-event times and classifies crash/hang."""

    def __init__(self) -> None:
        self._streams: dict[str, _StreamHealth] = {}

    def register(
        self,
        sensor_id: str,
        *,
        rate_hz: float,
        started_at: float,
        factor: float = 5.0,
        floor_s: float = 0.05,
    ) -> None:
        """Register a stream with a timeout derived from its nominal rate."""
        timeout = max(factor / rate_hz, floor_s) if rate_hz > 0 else floor_s
        self._streams[sensor_id] = _StreamHealth(timeout_s=timeout, last_event=started_at)

    def note_event(self, sensor_id: str, now: float) -> None:
        """Record that ``sensor_id`` produced an event at ``now`` (resets its timeout clock)."""
        self._streams[sensor_id].last_event = now

    def check(self, sensor_id: str, now: float, alive: bool) -> ErrorCode | None:
        """Classify a stream's health, or return ``None`` if healthy."""
        if not alive:
            return ErrorCode.DRIVER_CRASH
        health = self._streams[sensor_id]
        if now - health.last_event > health.timeout_s:
            return ErrorCode.WATCHDOG_TIMEOUT
        return None

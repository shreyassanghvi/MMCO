"""Restart backoff policy (design spec §6).

When a host dies the supervisor re-spawns it after a delay that grows exponentially per consecutive
attempt, capped at ``cap_s``. There is intentionally no give-up: a device gone for the whole session
just keeps retrying at the cap interval, so the stream settles into an all-gap state without a
spin-loop.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RestartPolicy:
    """Capped exponential backoff for host re-spawns."""

    base_s: float
    cap_s: float

    def backoff(self, attempt: int) -> float:
        """Return the delay before re-spawn for a zero-based consecutive ``attempt``."""
        return min(self.base_s * (2**attempt), self.cap_s)

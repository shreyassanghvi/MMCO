"""Stable device-identity resolution (design spec §6).

A sensor is bound to a *stable* identity (by-id path / ``VID:PID:serial``), not the transient device
index (e.g. ``/dev/video0``) that can change when a device re-enumerates after a reconnect. The
supervisor resolves a re-appeared device back to its sensor by identity, so a webcam that comes back
at a different index still records to the right stream.
"""

from __future__ import annotations


class IdentityRegistry:
    """Maps stable device identities to sensor ids, independent of device index."""

    def __init__(self) -> None:
        self._by_identity: dict[str, str] = {}

    def register(self, sensor_id: str, identity: str) -> None:
        """Bind a stable ``identity`` to a ``sensor_id``."""
        self._by_identity[identity] = sensor_id

    def resolve(self, identity: str) -> str:
        """Return the sensor bound to ``identity``; raise ``KeyError`` if unknown."""
        return self._by_identity[identity]

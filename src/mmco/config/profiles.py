"""Recording-profile resolution (design spec §5.1).

A recording profile says *how* to encode a stream of a given protocol (container, codec, crf, ...).
The session config carries protocol defaults under ``recording_profiles``; a sensor may override
individual keys. :func:`resolve_profile` merges the two — per-key override wins, absent keys fall
back to the protocol default — yielding the concrete profile a writer should honor.
"""

from __future__ import annotations


def resolve_profile(
    recording_profiles: dict, protocol: str | None, override: dict | None
) -> dict:
    """Merge the ``protocol`` default profile with a per-sensor ``override`` (override wins).

    Unknown protocols contribute no defaults, so the result is the ``override`` alone (or ``{}``).
    """
    default = recording_profiles.get(protocol, {}) if protocol is not None else {}
    return {**default, **(override or {})}

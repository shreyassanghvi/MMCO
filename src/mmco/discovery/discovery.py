"""Device discovery (design spec §3 component 7, §6 stable identity).

Enumerates the capture devices plugged into the box (cameras, mics, serial ports) and records each
one's **stable identity** (a by-id path / ``VID:PID:serial``) next to its transient device ``node``
(``/dev/video0``). The identity is what a sensor binds to, so reconnect-by-identity (Phase 5) keeps
working when a device re-enumerates at a new index.

Discovery is driven by injectable per-kind **enumerator** callables, each returning a list of
:class:`DiscoveredDevice`. The default enumerators are best-effort and Linux-oriented (they glob
``/dev``); they return an empty list when their source is absent, so on a non-Linux dev box
discovery simply yields nothing and the caller falls back to the simulated sensor. Tests inject
fakes (no hardware, no real ``/dev``) and run identically on every platform.
"""

from __future__ import annotations

import glob
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

Enumerator = Callable[[], list["DiscoveredDevice"]]


class DeviceKind(Enum):
    """The kind of capture device discovery can find."""

    VIDEO = "video"
    AUDIO = "audio"
    SERIAL = "serial"


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A device found on the box: its kind, transient node, and stable identity."""

    kind: DeviceKind
    node: str
    identity: str
    description: str = ""


def _enumerate_glob(pattern: str, kind: DeviceKind) -> list[DiscoveredDevice]:
    """Best-effort enumerator: each matching path is a device keyed by its own path.

    Without udev/by-id resolution (which arrives with the real drivers on Linux) the stable identity
    falls back to the node path; it is still stable for a device that does not re-enumerate.
    """
    devices: list[DiscoveredDevice] = []
    for node in sorted(glob.glob(pattern)):
        identity = node
        by_id = Path("/dev") / "by-id"  # populated by udev on Linux; absent elsewhere
        if by_id.is_dir():
            for link in by_id.iterdir():
                if link.is_symlink() and link.resolve() == Path(node).resolve():
                    identity = str(link)
                    break
        devices.append(DiscoveredDevice(kind=kind, node=node, identity=identity))
    return devices


def _enumerate_video() -> list[DiscoveredDevice]:
    return _enumerate_glob("/dev/video*", DeviceKind.VIDEO)


def _enumerate_serial() -> list[DiscoveredDevice]:
    return _enumerate_glob("/dev/ttyUSB*", DeviceKind.SERIAL) + _enumerate_glob(
        "/dev/ttyACM*", DeviceKind.SERIAL
    )


def _enumerate_audio() -> list[DiscoveredDevice]:
    return _enumerate_glob("/dev/snd/pcmC*c", DeviceKind.AUDIO)  # capture nodes


DEFAULT_ENUMERATORS: tuple[Enumerator, ...] = (
    _enumerate_video,
    _enumerate_audio,
    _enumerate_serial,
)


def discover_devices(
    *, enumerators: Sequence[Enumerator] = DEFAULT_ENUMERATORS
) -> list[DiscoveredDevice]:
    """Run every enumerator and return the flattened devices in deterministic order."""
    found: list[DiscoveredDevice] = []
    for enumerate_kind in enumerators:
        found.extend(enumerate_kind())
    return sorted(found, key=lambda d: (d.kind.value, d.identity))

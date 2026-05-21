"""The sensor-driver plugin contract (design spec §3.1).

Every sensor plugin subclasses :class:`SensorDriver`. The contract is deliberately narrow:

- ``open()`` / ``close()`` bracket the device's lifetime.
- ``read()`` returns a :class:`~mmco.core.events.DriverSample` — **payload bytes only**. A driver
  never touches shared memory; the host copies the payload into the ring buffer and stamps identity
  and time. This keeps drivers simple and the shared-memory lifecycle owned by the core.
- ``capabilities`` describes what the stream produces.
- ``health()`` reports a :class:`DriverHealth` heartbeat. It is a cheap, non-blocking status the
  driver maintains — **never** a blocking call the core makes into a possibly-hung driver. The
  supervisor's watchdog watches the heartbeat; it does not call into the driver to obtain it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from mmco.core.capabilities import Capabilities
from mmco.core.events import DriverSample


class DriverHealth(Enum):
    """Coarse driver liveness reported by ``SensorDriver.health()``."""

    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class SensorDriver(ABC):
    """Abstract base every sensor plugin implements."""

    @abstractmethod
    def open(self) -> None:
        """Acquire the device and prepare to read."""

    @abstractmethod
    def read(self) -> DriverSample:
        """Return the next sample's payload bytes and schema reference."""

    @abstractmethod
    def close(self) -> None:
        """Release the device."""

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        """Describe what this stream produces."""

    @abstractmethod
    def health(self) -> DriverHealth:
        """Return the current heartbeat status (cheap, non-blocking)."""

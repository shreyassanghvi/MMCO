"""A deterministic, hardware-free sensor driver (design spec §3.1, §9).

The simulated driver emits a tabular stream whose payload is simply the sample index, packed with
``struct``. Being deterministic, it doubles as the primary test fixture across the whole project.
Its **injectable failure modes** — ``crash`` (raise after N reads), ``slow`` (sleep per read), and
``hang`` (block in ``read()`` until ``close()`` releases it) — drive the graceful-degradation tests
in Phase 5 without needing flaky hardware.
"""

from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.driver import DeviceDisconnectedError, DriverHealth, SensorDriver
from mmco.core.events import DriverSample

_SCHEMA_REF = "sim.v1"
_VALUE = struct.Struct("<q")  # one int64 sample value


@dataclass(frozen=True, slots=True)
class SimConfig:
    """Configuration for a :class:`SimulatedDriver`."""

    sensor_id: str
    rate_hz: float
    failure: str | None = None  # None | "crash" | "slow" | "hang"
    failure_after: int = 0
    delay_s: float = 0.0


class SimulatedDriver(SensorDriver):
    """A deterministic tabular driver with optional injectable failure modes."""

    def __init__(self, config: SimConfig):
        self._config = config
        self._index = 0
        self._release = threading.Event()  # used to unblock a "hang"

    def open(self) -> None:
        self._release.clear()

    def read(self) -> DriverSample:
        cfg = self._config
        if cfg.failure == "crash" and self._index >= cfg.failure_after:
            raise RuntimeError(f"simulated driver crash at read {self._index}")
        if cfg.failure == "disconnect" and self._index >= cfg.failure_after:
            raise DeviceDisconnectedError(f"simulated device gone at read {self._index}")
        if cfg.failure == "slow":
            time.sleep(cfg.delay_s)
        if cfg.failure == "hang" and self._index >= cfg.failure_after:
            self._release.wait()  # blocks until close() releases it
        payload = _VALUE.pack(self._index)
        self._index += 1
        return DriverSample(payload=payload, payload_schema_ref=_SCHEMA_REF)

    def close(self) -> None:
        self._release.set()  # release any in-flight "hang"

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            type=StreamType.TABULAR,
            rate=self._config.rate_hz,
            schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
        )

    def health(self) -> DriverHealth:
        return DriverHealth.OK

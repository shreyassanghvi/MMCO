"""Event value types that cross the driver → host boundary (design spec §4.0).

A driver's ``read()`` returns a :class:`DriverSample` (payload bytes + a schema ref) and **nothing
else** — it never sets timing or identity. The host completes it into a :class:`SensorEvent` by
stamping ``sensor_id``, ``seq``, and ``t_acquire_ns``. :class:`EventMeta` is the small fixed-size
record that travels on the metadata queue, pointing at the payload's slot in the shared-memory ring.
"""

from __future__ import annotations

from dataclasses import dataclass


def _require_non_empty(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")


@dataclass(frozen=True, slots=True)
class DriverSample:
    """What a driver's ``read()`` returns: an opaque payload and the schema describing it."""

    payload: bytes
    payload_schema_ref: str


@dataclass(frozen=True, slots=True)
class SensorEvent:
    """A host-completed event: the driver's sample plus identity and acquisition time."""

    sensor_id: str
    seq: int
    t_acquire_ns: int
    payload: bytes
    payload_schema_ref: str

    def __post_init__(self) -> None:
        _require_non_empty("sensor_id", self.sensor_id)
        _require_non_negative("seq", self.seq)
        _require_non_negative("t_acquire_ns", self.t_acquire_ns)

    @classmethod
    def from_sample(
        cls,
        sample: DriverSample,
        *,
        sensor_id: str,
        seq: int,
        t_acquire_ns: int,
    ) -> SensorEvent:
        """Complete a driver-produced ``sample`` with host-assigned identity and timing."""
        return cls(
            sensor_id=sensor_id,
            seq=seq,
            t_acquire_ns=t_acquire_ns,
            payload=sample.payload,
            payload_schema_ref=sample.payload_schema_ref,
        )


@dataclass(frozen=True, slots=True)
class EventMeta:
    """The fixed-size metadata record carried on the queue, referencing a ring-buffer slot.

    ``gen`` is the slot's generation counter, used to detect a slot reused out from under a slow
    reader (backpressure / overwrite detection).
    """

    sensor_id: str
    seq: int
    t_acquire_ns: int
    slot: int
    length: int
    gen: int

    def __post_init__(self) -> None:
        _require_non_empty("sensor_id", self.sensor_id)
        _require_non_negative("seq", self.seq)
        _require_non_negative("t_acquire_ns", self.t_acquire_ns)
        _require_non_negative("slot", self.slot)
        _require_non_negative("length", self.length)
        _require_non_negative("gen", self.gen)

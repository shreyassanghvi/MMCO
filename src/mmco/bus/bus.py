"""Producer and consumer handles that compose the ring and the metadata queue (design spec §4.1).

A :class:`BusProducer` copies a payload into the :class:`~mmco.bus.ring.RingBuffer` and publishes
the matching :class:`~mmco.core.events.EventMeta` on the :class:`~mmco.bus.metaqueue.MetaQueue`. A
:class:`BusConsumer` pops a meta and reads the payload back, using the meta's ``gen`` to reject a
slot that was overwritten in the meantime. Drops are counted at both ends and never silent.
"""

from __future__ import annotations

from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.errors import ErrorCode
from mmco.core.events import EventMeta


class BusProducer:
    """Host-side handle: copies payloads into the ring and publishes metadata."""

    def __init__(self, ring: RingBuffer, metaqueue: MetaQueue):
        self._ring = ring
        self._metaqueue = metaqueue
        self.dropped = 0

    def publish(
        self, *, sensor_id: str, seq: int, t_acquire_ns: int, payload: bytes
    ) -> ErrorCode | None:
        """Write ``payload``, enqueue its meta; return an error code on backpressure, else ``None``."""
        ref = self._ring.write(payload)
        meta = EventMeta(
            sensor_id=sensor_id,
            seq=seq,
            t_acquire_ns=t_acquire_ns,
            slot=ref.slot,
            length=ref.length,
            gen=ref.gen,
        )
        if not self._metaqueue.put(meta):
            self.dropped += 1
            return ErrorCode.SHM_BUFFER_FULL
        return None


class BusConsumer:
    """Core-side handle: pops metadata and reads back the gen-checked payload."""

    def __init__(self, ring: RingBuffer, metaqueue: MetaQueue):
        self._ring = ring
        self._metaqueue = metaqueue
        self.dropped = 0

    def poll(self, timeout: float = 0.0) -> tuple[EventMeta, bytes] | None:
        """Return the next ``(meta, payload)`` pair, or ``None`` if none is available / it lapsed."""
        meta = self._metaqueue.get(timeout=timeout)
        if meta is None:
            return None
        payload = self._ring.read_slot(meta.slot, meta.gen, meta.length)
        if payload is None:
            self.dropped += 1
            return None
        return meta, payload

"""The metadata queue (design spec §4.0).

Small fixed-shape :class:`~mmco.core.events.EventMeta` records travel here while their payloads sit
in the shared-memory ring. This queue is the **ordering authority** for the bus: the consumer pops a
meta and uses its ``(slot, gen, length)`` to fetch the payload. Both ends are non-blocking — a full
queue is the system's backpressure signal, surfaced to the caller rather than blocking acquisition.
"""

from __future__ import annotations

import queue
from multiprocessing import Queue

from mmco.core.events import EventMeta


class MetaQueue:
    """A non-blocking wrapper over ``multiprocessing.Queue`` carrying ``EventMeta`` records."""

    def __init__(self, maxsize: int = 0):
        self._queue: Queue = Queue(maxsize)

    def put(self, meta: EventMeta) -> bool:
        """Enqueue ``meta`` without blocking; return ``False`` if the queue is full."""
        try:
            self._queue.put_nowait(meta)
            return True
        except queue.Full:
            return False

    def get(self, timeout: float = 0.0) -> EventMeta | None:
        """Dequeue the next record, waiting up to ``timeout`` seconds; ``None`` if none arrives."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        """Release the underlying queue without blocking on its feeder thread."""
        self._queue.cancel_join_thread()
        self._queue.close()

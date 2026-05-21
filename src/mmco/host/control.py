"""Control and log channels between the core and a driver host (design spec §3.1).

:class:`Control` carries a single stop signal core → host (over a ``multiprocessing.Event``).
:class:`LogChannel` carries the host's :class:`~mmco.core.logevent.LogEvent`s host → core (over a
``multiprocessing.Queue``). Both are picklable so the core can hand them to a spawned child as
``Process`` arguments; both ends are non-blocking so neither side ever stalls the other.
"""

from __future__ import annotations

import multiprocessing as mp
import queue

from mmco.core.logevent import LogEvent


class Control:
    """A one-way stop signal from the core to a driver host."""

    def __init__(self) -> None:
        self._stop = mp.Event()

    def request_stop(self) -> None:
        """Ask the host to finish its current iteration and exit."""
        self._stop.set()

    def stop_requested(self) -> bool:
        """Return whether a stop has been requested."""
        return self._stop.is_set()


class LogChannel:
    """A host → core channel for ``LogEvent`` records."""

    def __init__(self, maxsize: int = 0):
        self._queue: mp.Queue = mp.Queue(maxsize)

    def emit(self, event: LogEvent) -> bool:
        """Send a log event without blocking; return ``False`` if the channel is full."""
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            return False

    def drain(self, timeout: float = 0.0) -> list[LogEvent]:
        """Collect all currently available events, waiting up to ``timeout`` for the first."""
        events: list[LogEvent] = []
        try:
            events.append(self._queue.get(timeout=timeout))
        except queue.Empty:
            return events
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def close(self) -> None:
        """Release the underlying queue without blocking on its feeder thread."""
        self._queue.cancel_join_thread()
        self._queue.close()

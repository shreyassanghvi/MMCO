"""The per-stream writer contract and its type registry (design spec §5).

A :class:`StreamWriter` turns a stream's events into one native file, tracking the first/last
``t_event`` so the recorder can build a manifest segment. Writers are selected per
:class:`~mmco.core.capabilities.StreamType` through a small registry; merging this with the driver
entry-point plugin mechanism (so a stream type ships driver + writer together) is Phase 8.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from mmco.core.capabilities import Capabilities, StreamType


class StreamWriter(ABC):
    """Writes one stream's events to a single file and tracks its time span."""

    def __init__(self, *, capabilities: Capabilities, file_path: str):
        self._capabilities = capabilities
        self._file_path = file_path
        self._start: int | None = None
        self._end: int | None = None

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def start_timestamp(self) -> int | None:
        return self._start

    @property
    def end_timestamp(self) -> int | None:
        return self._end

    def _observe(self, t_event_ns: int) -> None:
        """Record ``t_event_ns`` as the latest (and, if first, earliest) timestamp seen."""
        if self._start is None:
            self._start = t_event_ns
        self._end = t_event_ns

    @abstractmethod
    def open(self) -> None:
        """Prepare to write (open the file / buffers)."""

    @abstractmethod
    def write_event(self, t_event_ns: int, payload: bytes) -> None:
        """Append one event's payload, stamped with its corrected ``t_event``."""

    @abstractmethod
    def close(self) -> None:
        """Flush and finalize the file."""


_REGISTRY: dict[StreamType, type[StreamWriter]] = {}


def register_writer(stream_type: StreamType, cls: type[StreamWriter]) -> None:
    """Register the writer class to use for a given stream type."""
    _REGISTRY[stream_type] = cls


def writer_for(
    stream_type: StreamType, *, capabilities: Capabilities, file_path: str
) -> StreamWriter:
    """Construct the registered writer for ``stream_type``; raise if none is registered."""
    try:
        cls = _REGISTRY[stream_type]
    except KeyError:
        raise ValueError(f"no writer registered for {stream_type}") from None
    return cls(capabilities=capabilities, file_path=file_path)

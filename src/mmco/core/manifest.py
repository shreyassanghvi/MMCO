"""The session manifest model — the alignment contract an ML loader reads (design spec §5).

A manifest records, per stream, where the data landed and where it didn't: ``segments`` are the
written files (one stream becomes multiple files across a disconnect/reconnect, since mp4/wav are
not safely appendable mid-session), and ``gaps`` preserve the holes between them with the
:class:`~mmco.core.errors.ErrorCode` explaining why. Serialization is symmetric JSON: ``StreamType``
goes out by name and ``ErrorCode`` by its stable ``.code`` string, so the on-disk shape stays
stable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from mmco.core.capabilities import Capabilities, StreamType
from mmco.core.clock import ClockAnchor
from mmco.core.errors import ErrorCode


@dataclass(frozen=True, slots=True)
class Segment:
    """One written file for a stream, with its covered monotonic time range."""

    file_path: str
    start_timestamp: int
    end_timestamp: int
    block_index: int

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "block_index": self.block_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Segment:
        return cls(
            file_path=data["file_path"],
            start_timestamp=data["start_timestamp"],
            end_timestamp=data["end_timestamp"],
            block_index=data["block_index"],
        )


@dataclass(frozen=True, slots=True)
class Gap:
    """A hole in a stream's coverage, with the reason and error code that caused it."""

    start: int
    end: int
    reason: str
    code: ErrorCode

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "reason": self.reason,
            "code": self.code.code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Gap:
        return cls(
            start=data["start"],
            end=data["end"],
            reason=data["reason"],
            code=ErrorCode.from_code(data["code"]),
        )


@dataclass(frozen=True, slots=True)
class StreamBlock:
    """Everything the manifest records about one sensor's stream."""

    sensor_id: str
    type: StreamType
    capabilities: Capabilities
    latency_offset: int
    dropped: int  # count of events dropped for this stream (0 = none)
    segments: tuple[Segment, ...]
    gaps: tuple[Gap, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "sensor_id": self.sensor_id,
            "type": self.type.name,
            "capabilities": self.capabilities.to_dict(),
            "latency_offset": self.latency_offset,
            "dropped": self.dropped,
            "segments": [s.to_dict() for s in self.segments],
            "gaps": [g.to_dict() for g in self.gaps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> StreamBlock:
        return cls(
            sensor_id=data["sensor_id"],
            type=StreamType[data["type"]],
            capabilities=Capabilities.from_dict(data["capabilities"]),
            latency_offset=data["latency_offset"],
            dropped=data["dropped"],
            segments=tuple(Segment.from_dict(s) for s in data["segments"]),
            gaps=tuple(Gap.from_dict(g) for g in data["gaps"]),
        )


@dataclass(frozen=True, slots=True)
class SessionManifest:
    """The top-level session record: identity, clock anchor, output dir, and per-stream blocks."""

    session_id: str
    anchor: ClockAnchor
    output_dir: str
    streams: tuple[StreamBlock, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "anchor": {
                "monotonic_ns": self.anchor.monotonic_ns,
                "wall_ns": self.anchor.wall_ns,
            },
            "output_dir": self.output_dir,
            "streams": [b.to_dict() for b in self.streams],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SessionManifest:
        anchor = ClockAnchor(
            monotonic_ns=data["anchor"]["monotonic_ns"],
            wall_ns=data["anchor"]["wall_ns"],
        )
        return cls(
            session_id=data["session_id"],
            anchor=anchor,
            output_dir=data["output_dir"],
            streams=tuple(StreamBlock.from_dict(b) for b in data["streams"]),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> SessionManifest:
        return cls.from_dict(json.loads(text))

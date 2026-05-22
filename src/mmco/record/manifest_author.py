"""Assembles and writes the session manifest (design spec §5).

The recorder feeds the author as a session runs — one ``add_stream`` per sensor, an ``add_segment``
per file written, and a final ``set_dropped`` count — then ``write`` assembles a Phase 1
:class:`~mmco.core.manifest.SessionManifest` and serializes it to ``manifest.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mmco.core.capabilities import Capabilities, StreamType
from mmco.core.clock import ClockAnchor
from mmco.core.manifest import Gap, Segment, SessionManifest, StreamBlock


@dataclass
class _StreamState:
    type: StreamType
    capabilities: Capabilities
    latency_offset: int
    dropped: int = 0
    segments: list[Segment] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)


class ManifestAuthor:
    """Accumulates per-stream segments/drops over a session and writes ``manifest.json``."""

    def __init__(self, *, session_id: str, output_dir: str, anchor: ClockAnchor):
        self._session_id = session_id
        self._output_dir = output_dir
        self._anchor = anchor
        self._streams: dict[str, _StreamState] = {}

    def add_stream(
        self,
        sensor_id: str,
        stream_type: StreamType,
        capabilities: Capabilities,
        latency_offset: int,
    ) -> None:
        """Register a stream with its capabilities and measured latency offset."""
        self._streams[sensor_id] = _StreamState(
            type=stream_type, capabilities=capabilities, latency_offset=latency_offset
        )

    def add_segment(self, sensor_id: str, segment: Segment) -> None:
        """Append a written file's segment to a stream."""
        self._streams[sensor_id].segments.append(segment)

    def add_gap(self, sensor_id: str, gap: Gap) -> None:
        """Append a coverage gap (a fault/reconnect hole) to a stream."""
        self._streams[sensor_id].gaps.append(gap)

    def set_dropped(self, sensor_id: str, dropped: int) -> None:
        """Set a stream's dropped-event count."""
        self._streams[sensor_id].dropped = dropped

    def build(self) -> SessionManifest:
        """Assemble the accumulated state into a ``SessionManifest``."""
        blocks = tuple(
            StreamBlock(
                sensor_id=sensor_id,
                type=state.type,
                capabilities=state.capabilities,
                latency_offset=state.latency_offset,
                dropped=state.dropped,
                segments=tuple(state.segments),
                gaps=tuple(state.gaps),
            )
            for sensor_id, state in self._streams.items()
        )
        return SessionManifest(
            session_id=self._session_id,
            anchor=self._anchor,
            output_dir=self._output_dir,
            streams=blocks,
        )

    def write(self, path: str) -> SessionManifest:
        """Write ``manifest.json`` to ``path`` and return the assembled manifest."""
        manifest = self.build()
        Path(path).write_text(manifest.to_json())
        return manifest

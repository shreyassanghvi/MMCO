"""The recorder: route drained bus events to per-stream writers and a manifest (spec §4.1, §5).

The recorder polls a :class:`~mmco.bus.bus.BusConsumer`, routes each event by ``sensor_id`` to that
sensor's writer (created lazily under ``recordings/<session_id>/``), and writes the corrected
``t_event = t_acquire − offset``. On stop it closes the writers, turns each into a manifest segment,
records dropped counts, and writes ``manifest.json``.
"""

from __future__ import annotations

from pathlib import Path

from mmco.bus.bus import BusConsumer
from mmco.core.capabilities import Capabilities, StreamType
from mmco.core.clock import ClockAnchor, OffsetRegistry
from mmco.core.manifest import Segment
from mmco.paths import manifest_path, session_dir
from mmco.record import parquet_writer  # noqa: F401  (registers the tabular writer)
from mmco.record.manifest_author import ManifestAuthor
from mmco.record.writer import StreamWriter, writer_for

# File suffix per stream type (more types arrive with their writers in later phases).
_SUFFIX: dict[StreamType, str] = {StreamType.TABULAR: "parquet"}


class Recorder:
    """Drains the bus into per-stream files plus a session manifest."""

    def __init__(
        self,
        *,
        consumer: BusConsumer,
        capabilities: dict[str, Capabilities],
        offsets: OffsetRegistry,
        session_id: str,
        base_dir: Path,
        anchor: ClockAnchor,
    ):
        self._consumer = consumer
        self._capabilities = capabilities
        self._offsets = offsets
        self._session_id = session_id
        self._session_dir = session_dir(base_dir, session_id)
        self._author = ManifestAuthor(
            session_id=session_id, output_dir=str(self._session_dir), anchor=anchor
        )
        self._writers: dict[str, StreamWriter] = {}
        self._rel_paths: dict[str, str] = {}

    def start(self) -> None:
        """Create the session directory."""
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def _writer_for(self, sensor_id: str) -> StreamWriter:
        writer = self._writers.get(sensor_id)
        if writer is not None:
            return writer
        caps = self._capabilities[sensor_id]
        rel = f"{sensor_id}-000.{_SUFFIX[caps.type]}"
        writer = writer_for(
            caps.type, capabilities=caps, file_path=str(self._session_dir / rel)
        )
        writer.open()
        self._author.add_stream(
            sensor_id, caps.type, caps, latency_offset=self._offsets.get(sensor_id)
        )
        self._writers[sensor_id] = writer
        self._rel_paths[sensor_id] = rel
        return writer

    def record_available(self, timeout: float = 0.0) -> bool:
        """Poll once; route and write one event if present. Return whether one was recorded."""
        result = self._consumer.poll(timeout=timeout)
        if result is None:
            return False
        meta, payload = result
        t_event = self._offsets.event_time(meta.sensor_id, meta.t_acquire_ns)
        self._writer_for(meta.sensor_id).write_event(t_event, payload)
        return True

    def stop(self) -> Path:
        """Close writers, finalize segments + drops, and write ``manifest.json``."""
        sensor_ids = list(self._writers)
        for sensor_id in sensor_ids:
            writer = self._writers[sensor_id]
            writer.close()
            if writer.start_timestamp is not None:
                self._author.add_segment(
                    sensor_id,
                    Segment(
                        file_path=self._rel_paths[sensor_id],
                        start_timestamp=writer.start_timestamp,
                        end_timestamp=writer.end_timestamp,
                        block_index=0,
                    ),
                )
            # Single-stream sessions can attribute the consumer's drops to that stream;
            # per-sensor drop attribution for multi-stream sessions arrives in Phase 5.
            if len(sensor_ids) == 1:
                self._author.set_dropped(sensor_id, self._consumer.dropped)
        path = manifest_path(self._session_dir)
        self._author.write(str(path))
        return path

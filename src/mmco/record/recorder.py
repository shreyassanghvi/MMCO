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
from mmco.core.errors import ErrorCode
from mmco.core.manifest import Gap, Segment
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
        self._block_index: dict[str, int] = {}
        self._registered: set[str] = set()
        self._seen: set[str] = set()

    def start(self) -> None:
        """Create the session directory."""
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def _writer_for(self, sensor_id: str) -> StreamWriter:
        writer = self._writers.get(sensor_id)
        if writer is not None:
            return writer
        caps = self._capabilities[sensor_id]
        index = self._block_index.get(sensor_id, 0)
        rel = f"{sensor_id}-{index:03d}.{_SUFFIX[caps.type]}"
        writer = writer_for(
            caps.type, capabilities=caps, file_path=str(self._session_dir / rel)
        )
        writer.open()
        if sensor_id not in self._registered:
            self._author.add_stream(
                sensor_id, caps.type, caps, latency_offset=self._offsets.get(sensor_id)
            )
            self._registered.add(sensor_id)
        self._writers[sensor_id] = writer
        self._rel_paths[sensor_id] = rel
        self._block_index[sensor_id] = index
        self._seen.add(sensor_id)
        return writer

    def _finalize_writer(self, sensor_id: str) -> None:
        """Close the current writer for a sensor and record its segment (if it has data)."""
        writer = self._writers.pop(sensor_id, None)
        if writer is None:
            return
        writer.close()
        if writer.start_timestamp is not None:
            self._author.add_segment(
                sensor_id,
                Segment(
                    file_path=self._rel_paths[sensor_id],
                    start_timestamp=writer.start_timestamp,
                    end_timestamp=writer.end_timestamp,
                    block_index=self._block_index[sensor_id],
                ),
            )

    def record_available(self, timeout: float = 0.0) -> bool:
        """Poll once; route and write one event if present. Return whether one was recorded."""
        result = self._consumer.poll(timeout=timeout)
        if result is None:
            return False
        meta, payload = result
        t_event = self._offsets.event_time(meta.sensor_id, meta.t_acquire_ns)
        self._writer_for(meta.sensor_id).write_event(t_event, payload)
        return True

    def open_gap(
        self, sensor_id: str, *, start: int, end: int, reason: str, code: ErrorCode
    ) -> None:
        """Close the sensor's current segment, record a coded gap, and resume into a new segment."""
        self._finalize_writer(sensor_id)
        self._author.add_gap(
            sensor_id, Gap(start=start, end=end, reason=reason, code=code)
        )
        self._block_index[sensor_id] = self._block_index.get(sensor_id, 0) + 1

    def stop(self) -> Path:
        """Close writers, finalize segments + drops, and write ``manifest.json``."""
        for sensor_id in list(self._writers):
            self._finalize_writer(sensor_id)
        # Single-stream sessions can attribute the consumer's drops to that stream;
        # per-sensor drop attribution for multi-stream sessions arrives later.
        if len(self._seen) == 1:
            only = next(iter(self._seen))
            self._author.set_dropped(only, self._consumer.dropped)
        path = manifest_path(self._session_dir)
        self._author.write(str(path))
        return path

"""Video writer (PyAV/ffmpeg) for video streams (design spec §5).

Encodes raw RGB frames to a native container (mp4/mkv) using a codec/crf taken from the sensor's
resolved recording profile. Real cameras don't deliver at exactly nominal fps and any drop breaks
uniform spacing, so the writer also emits a **per-frame timestamp sidecar** (a parquet of frame
index + corrected ``t_event``) next to the media file — the video analog of the parquet writer's
per-row ``t_event`` column. The ML loader reads the sidecar to place each frame on the timeline.
"""

from __future__ import annotations

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from mmco.core.capabilities import Capabilities, StreamType
from mmco.record.writer import StreamWriter, register_writer

_DEFAULT_CODEC = "libx264"
_DEFAULT_CRF = 23
_ENCODE_PIX_FMT = "yuv420p"  # h264 needs a YUV plane; PyAV reformats rgb24 frames on encode


def sidecar_path(file_path: str) -> str:
    """Return the per-frame timestamp sidecar path for a media ``file_path``."""
    return f"{file_path}.timestamps.parquet"


class VideoWriter(StreamWriter):
    """Encodes raw frames to a container and writes a per-frame ``t_event`` sidecar."""

    def __init__(
        self, *, capabilities: Capabilities, file_path: str, profile: dict | None = None
    ):
        super().__init__(capabilities=capabilities, file_path=file_path, profile=profile)
        schema = capabilities.schema
        self._width = schema.width
        self._height = schema.height
        self._pixel_format = schema.pixel_format
        self._container = None
        self._stream = None
        self._t_events: list[int] = []

    def open(self) -> None:
        self._t_events = []
        codec = self._profile.get("codec", _DEFAULT_CODEC)
        crf = self._profile.get("crf", _DEFAULT_CRF)
        self._container = av.open(self._file_path, mode="w")
        rate = int(self._capabilities.rate or 30)
        self._stream = self._container.add_stream(codec, rate=rate)
        self._stream.width = self._width
        self._stream.height = self._height
        self._stream.pix_fmt = _ENCODE_PIX_FMT
        self._stream.options = {"crf": str(crf)}

    def write_event(self, t_event_ns: int, payload: bytes) -> None:
        array = np.frombuffer(payload, dtype=np.uint8).reshape(
            (self._height, self._width, 3)
        )
        frame = av.VideoFrame.from_ndarray(array, format=self._pixel_format)
        for packet in self._stream.encode(frame):
            self._container.mux(packet)
        self._observe(t_event_ns)
        self._t_events.append(t_event_ns)

    def close(self) -> None:
        for packet in self._stream.encode():  # flush the encoder
            self._container.mux(packet)
        self._container.close()
        table = pa.table(
            {
                "frame_index": pa.array(range(len(self._t_events)), type=pa.int64()),
                "t_event": pa.array(self._t_events, type=pa.int64()),
            }
        )
        pq.write_table(table, sidecar_path(self._file_path))


register_writer(StreamType.VIDEO, VideoWriter)

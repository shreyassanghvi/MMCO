"""Stream capabilities and per-type payload schema descriptors (design spec §4.0).

Every sensor declares a :class:`Capabilities`: its :class:`StreamType`, a nominal ``rate`` (Hz, or
``None`` when not fixed), and a schema descriptor that tells a consumer how to interpret the payload
bytes. The schema descriptor's concrete type must match the stream type — that invariant is enforced
at construction so a malformed capability can never reach a writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StreamType(Enum):
    """The kind of data a stream carries."""

    VIDEO = "video"
    AUDIO = "audio"
    TABULAR = "tabular"


@dataclass(frozen=True, slots=True)
class Column:
    """One column of a tabular stream."""

    name: str
    dtype: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "dtype": self.dtype}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Column:
        return cls(name=data["name"], dtype=data["dtype"])


@dataclass(frozen=True, slots=True)
class TabularSchema:
    """Ordered columns for a tabular stream (e.g. IMU rows)."""

    columns: tuple[Column, ...]

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("TabularSchema requires at least one column")

    def to_dict(self) -> dict[str, object]:
        return {"columns": [c.to_dict() for c in self.columns]}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> TabularSchema:
        columns = tuple(Column.from_dict(c) for c in data["columns"])
        return cls(columns=columns)


@dataclass(frozen=True, slots=True)
class VideoSchema:
    """Pixel/encoding descriptor for a video stream."""

    codec_or_raw: str
    width: int
    height: int
    pixel_format: str

    def to_dict(self) -> dict[str, object]:
        return {
            "codec_or_raw": self.codec_or_raw,
            "width": self.width,
            "height": self.height,
            "pixel_format": self.pixel_format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> VideoSchema:
        return cls(
            codec_or_raw=data["codec_or_raw"],
            width=data["width"],
            height=data["height"],
            pixel_format=data["pixel_format"],
        )


@dataclass(frozen=True, slots=True)
class AudioSchema:
    """Sample-format descriptor for an audio stream."""

    sample_rate: int
    channels: int
    sample_format: str

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_format": self.sample_format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AudioSchema:
        return cls(
            sample_rate=data["sample_rate"],
            channels=data["channels"],
            sample_format=data["sample_format"],
        )


PayloadSchema = TabularSchema | VideoSchema | AudioSchema

_SCHEMA_FOR_TYPE: dict[StreamType, type] = {
    StreamType.VIDEO: VideoSchema,
    StreamType.AUDIO: AudioSchema,
    StreamType.TABULAR: TabularSchema,
}


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What a sensor produces: stream type, nominal rate, and matching payload schema."""

    type: StreamType
    rate: float | None
    schema: PayloadSchema

    def __post_init__(self) -> None:
        expected = _SCHEMA_FOR_TYPE[self.type]
        if not isinstance(self.schema, expected):
            raise ValueError(
                f"{self.type.name} stream requires a {expected.__name__}, "
                f"got {type(self.schema).__name__}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type.name,
            "rate": self.rate,
            "schema": self.schema.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Capabilities:
        stream_type = StreamType[data["type"]]
        schema = _SCHEMA_FOR_TYPE[stream_type].from_dict(data["schema"])
        return cls(type=stream_type, rate=data["rate"], schema=schema)

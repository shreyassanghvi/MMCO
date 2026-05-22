"""USB webcam driver (V4L2) opening by stable identity (design spec §3.1, §6, §9).

A webcam is bound to a **stable identity** (a by-id path / ``VID:PID:serial``), not the transient
``/dev/videoN`` index that changes when the device re-enumerates after a reconnect. ``open()``
resolves the identity to the current node and starts a frame source; ``read()`` returns one raw
frame's bytes (the host copies them into the ring and stamps time); a vanished device surfaces as
:class:`~mmco.core.driver.DeviceDisconnectedError` (``E004``).

V4L2 only exists on Linux, so the frame source and the identity resolver are chosen **by name**
(``backend="v4l2"`` | ``"fake"``) from plain config fields, never a serialized callable. That keeps
the driver safe to ship to a child process under ``spawn``. The deterministic ``fake`` backend
drives every unit test with no hardware (synthetic frames, a scriptable disconnect, and a scriptable
node on re-open); the real V4L2 backend is thin and hardware-validated via the manual checklist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mmco.core.capabilities import Capabilities, StreamType, VideoSchema
from mmco.core.driver import DeviceDisconnectedError, DriverHealth, SensorDriver
from mmco.core.events import DriverSample

_PIXEL_FORMAT = "rgb24"
_BYTES_PER_PIXEL = 3  # rgb24
_SCHEMA_REF = "webcam.raw.v1"


@dataclass(frozen=True, slots=True)
class WebcamConfig:
    """Configuration for a :class:`WebcamDriver`; ``backend`` selects the frame source by name."""

    sensor_id: str
    identity: str
    width: int
    height: int
    fps: float
    backend: str = "v4l2"
    pixel_format: str = _PIXEL_FORMAT
    # ``fake`` backend only:
    disconnect_after: int | None = None
    fake_nodes: tuple[str, ...] = field(default_factory=tuple)


class _FakeResolver:
    """Returns scripted nodes for a stable identity, advancing one step per ``open``."""

    def __init__(self, nodes: tuple[str, ...]):
        self._nodes = nodes or ("/dev/video-fake",)
        self._index = 0

    def resolve(self, identity: str) -> str:
        node = self._nodes[min(self._index, len(self._nodes) - 1)]
        self._index += 1
        return node


class _V4L2Resolver:
    """Resolves a stable identity to its current ``/dev/videoN`` via ``/dev/v4l/by-id`` (Linux)."""

    def resolve(self, identity: str) -> str:
        from pathlib import Path  # local import: only needed on the hardware path

        candidate = Path(identity)
        return str(candidate.resolve() if candidate.exists() else candidate)


class _FakeBackend:
    """A deterministic synthetic frame source with an optional scripted disconnect."""

    def __init__(self, *, frame_size: int, disconnect_after: int | None):
        self._frame_size = frame_size
        self._disconnect_after = disconnect_after
        self._index = 0

    def open(self, node: str) -> None:
        self._index = 0

    def read(self) -> bytes:
        if self._disconnect_after is not None and self._index >= self._disconnect_after:
            raise DeviceDisconnectedError(f"fake webcam gone at frame {self._index}")
        frame = bytes((self._index % 256,)) * self._frame_size
        self._index += 1
        return frame

    def close(self) -> None:
        pass


class _V4L2Backend:
    """A thin real V4L2 frame source via PyAV (hardware-validated; lazily imports ``av``)."""

    def __init__(self, *, width: int, height: int, fps: float, pixel_format: str):
        self._width = width
        self._height = height
        self._fps = fps
        self._pixel_format = pixel_format
        self._container = None
        self._frames = None

    def open(self, node: str) -> None:
        import av  # local import: only the hardware path needs PyAV/ffmpeg

        self._container = av.open(
            node,
            format="v4l2",
            options={
                "video_size": f"{self._width}x{self._height}",
                "framerate": str(self._fps),
            },
        )
        self._frames = self._container.decode(video=0)

    def read(self) -> bytes:
        try:
            frame = next(self._frames)
        except StopIteration as exc:
            raise DeviceDisconnectedError("v4l2 stream ended") from exc
        return bytes(frame.to_ndarray(format=self._pixel_format).tobytes())

    def close(self) -> None:
        if self._container is not None:
            self._container.close()


def _make_resolver(config: WebcamConfig):
    if config.backend == "fake":
        return _FakeResolver(config.fake_nodes)
    return _V4L2Resolver()


def _make_backend(config: WebcamConfig):
    if config.backend == "fake":
        frame_size = config.width * config.height * _BYTES_PER_PIXEL
        return _FakeBackend(frame_size=frame_size, disconnect_after=config.disconnect_after)
    return _V4L2Backend(
        width=config.width,
        height=config.height,
        fps=config.fps,
        pixel_format=config.pixel_format,
    )


class WebcamDriver(SensorDriver):
    """A V4L2 webcam plugin that binds to a stable identity and reads raw frames."""

    def __init__(self, config: WebcamConfig):
        self._config = config
        self._resolver = _make_resolver(config)
        self._backend = None
        self._node: str | None = None

    def open(self) -> None:
        self._node = self._resolver.resolve(self._config.identity)
        self._backend = _make_backend(self._config)
        self._backend.open(self._node)

    def read(self) -> DriverSample:
        return DriverSample(payload=self._backend.read(), payload_schema_ref=_SCHEMA_REF)

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()

    @property
    def node(self) -> str | None:
        """The device node resolved at the most recent ``open`` (transient; for diagnostics)."""
        return self._node

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            type=StreamType.VIDEO,
            rate=self._config.fps,
            schema=VideoSchema(
                codec_or_raw="raw",
                width=self._config.width,
                height=self._config.height,
                pixel_format=self._config.pixel_format,
            ),
        )

    def health(self) -> DriverHealth:
        return DriverHealth.OK

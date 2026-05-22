"""The ``mmco`` command-line entry point (design spec §7).

``mmco run [sensors.yaml] [--seconds N]`` boots a :class:`~mmco.supervisor.supervisor.Supervisor`,
ticks the session, and finalizes the manifest + log + summary on completion or on Ctrl-C. The
bounded ``--seconds`` makes the command testable and gives the demo a definite end. With **no config
path** it auto-discovers devices and builds a default session, falling back to the simulated sensor
when nothing runnable is found (spec §7).

A small **simulated-only** driver registry maps a config's ``driver`` name to a builder that
produces a :class:`SensorSpec`. Real drivers ship via an entry-point plugin registry (Phase 9+);
this dict is the seam, and its keys are the ``runnable_drivers`` the default-session builder filters
to. A live status table is printed each tick (best-effort, added in Task 7.4).

Detached ``mmco stop`` / ``mmco status`` against a separately-running daemon need an IPC channel
(socket/pidfile) that is out of scope this phase; only the in-process ``run`` and the status
*renderer* land here (see the Phase 7 plan's locked decisions).
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from mmco.cli.status_view import render_status
from mmco.config.config import ConfigError, SensorConfig, SessionConfig, load_config
from mmco.config.profiles import resolve_profile
from mmco.core.capabilities import (
    Capabilities,
    Column,
    StreamType,
    TabularSchema,
    VideoSchema,
)
from mmco.discovery.default_session import build_default_session
from mmco.discovery.discovery import discover_devices
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.drivers.webcam_v4l2 import WebcamConfig, WebcamDriver
from mmco.paths import session_dir
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.supervisor import SensorSpec, Supervisor

_DEFAULT_SECONDS = 10.0
_TICK_S = 0.05
_STATUS_EVERY_S = 1.0
_N_SLOTS = 16
_SLOT_SIZE = 64
_DEFAULT_OUTPUT_DIR = "."
# Default webcam geometry when discovery doesn't specify one (real cameras override on open).
_CAM_WIDTH, _CAM_HEIGHT = 640, 480
_CAM_VIDEO_SLOTS = 8


def _build_simulated(sc: SensorConfig) -> SensorSpec:
    """Map a ``simulated`` sensor config to a runnable :class:`SensorSpec`."""
    capabilities = Capabilities(
        type=StreamType.TABULAR,
        rate=sc.rate_hz,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )
    return SensorSpec(
        sensor_id=sc.id,
        identity=sc.identity or sc.id,
        rate_hz=sc.rate_hz,
        n_slots=_N_SLOTS,
        slot_size=_SLOT_SIZE,
        driver_factory=SimulatedDriver,
        driver_config=SimConfig(sensor_id=sc.id, rate_hz=sc.rate_hz),
        capabilities=capabilities,
    )


def _build_webcam(sc: SensorConfig) -> SensorSpec:
    """Map a webcam sensor config to a runnable :class:`SensorSpec` (real V4L2 backend)."""
    capabilities = Capabilities(
        type=StreamType.VIDEO,
        rate=sc.rate_hz,
        schema=VideoSchema(
            codec_or_raw="raw",
            width=_CAM_WIDTH,
            height=_CAM_HEIGHT,
            pixel_format="rgb24",
        ),
    )
    return SensorSpec(
        sensor_id=sc.id,
        identity=sc.identity or sc.id,
        rate_hz=sc.rate_hz,
        n_slots=_CAM_VIDEO_SLOTS,
        slot_size=_CAM_WIDTH * _CAM_HEIGHT * 3,
        driver_factory=WebcamDriver,
        driver_config=WebcamConfig(
            sensor_id=sc.id,
            identity=sc.identity or sc.id,
            width=_CAM_WIDTH,
            height=_CAM_HEIGHT,
            fps=sc.rate_hz,
            backend="v4l2",
        ),
        capabilities=capabilities,
    )


# The seam (a future entry-point plugin registry) mapping driver names to spec builders.
_DRIVER_REGISTRY: dict[str, Callable[[SensorConfig], SensorSpec]] = {
    "simulated": _build_simulated,
    "webcam_v4l2": _build_webcam,
}


def build_spec(sc: SensorConfig, *, recording_profiles: dict | None = None) -> SensorSpec:
    """Resolve a sensor config to a :class:`SensorSpec`, attaching its offset + resolved profile."""
    builder = _DRIVER_REGISTRY.get(sc.driver)
    if builder is None:
        raise ConfigError(f"unknown driver {sc.driver!r} for sensor {sc.id!r}")
    profile = resolve_profile(recording_profiles or {}, sc.protocol, sc.profile_override)
    return replace(builder(sc), latency_offset_ns=sc.latency_offset_ns, profile=profile)


def runnable_driver_names() -> set[str]:
    """The driver names the CLI can actually run — the set the default builder filters to."""
    return set(_DRIVER_REGISTRY)


def _new_session_id() -> str:
    return datetime.now(UTC).strftime("sess-%Y%m%dT%H%M%SZ")


def run_session(
    config: SessionConfig, *, max_seconds: float, session_id: str | None = None
) -> Path:
    """Record a configured session for up to ``max_seconds``; finalize and return its directory.

    Finalizes (manifest + log + summary) on normal completion or on ``KeyboardInterrupt``.
    """
    session_id = session_id or _new_session_id()
    base_dir = Path(config.output_dir)
    specs = [
        build_spec(sc, recording_profiles=config.recording_profiles) for sc in config.sensors
    ]
    supervisor = Supervisor(
        session_id=session_id,
        base_dir=base_dir,
        specs=specs,
        policy=RestartPolicy(base_s=0.5, cap_s=5.0),
    )
    supervisor.start()
    next_status = time.monotonic()
    try:
        deadline = time.monotonic() + max_seconds
        while time.monotonic() < deadline:
            supervisor.tick()
            now = time.monotonic()
            if now >= next_status:
                print(render_status(supervisor.snapshot()))
                next_status = now + _STATUS_EVERY_S
            time.sleep(_TICK_S)
    except KeyboardInterrupt:
        print("\nstopping (Ctrl-C) — finalizing session...")
    finally:
        supervisor.stop()
    return session_dir(base_dir, session_id)


def main(argv: list[str] | None = None) -> int:
    """Parse args and dispatch. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="mmco", description="MMCO capture-box control surface.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="record a session (auto-discovers when no config is given)")
    run.add_argument(
        "config", nargs="?", default=None,
        help="path to sensors.yaml; omit to auto-discover devices",
    )
    run.add_argument(
        "--seconds", type=float, default=_DEFAULT_SECONDS,
        help="how long to record before finalizing (default: %(default)s)",
    )
    run.add_argument(
        "--output-dir", default=_DEFAULT_OUTPUT_DIR,
        help="where to write recordings when auto-discovering (default: %(default)s)",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        try:
            config = _resolve_config(args.config, output_dir=args.output_dir)
        except ConfigError as exc:
            print(f"{exc.code.code} {exc}")
            return 1
        sdir = run_session(config, max_seconds=args.seconds)
        print(f"session written to {sdir}")
        return 0
    return 2


def _resolve_config(config_path: str | None, *, output_dir: str) -> SessionConfig:
    """An explicit config always wins; otherwise auto-discover and build a default session."""
    if config_path is not None:
        return load_config(config_path)
    devices = discover_devices()
    return build_default_session(
        devices, output_dir=output_dir, runnable_drivers=runnable_driver_names()
    )

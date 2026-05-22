"""The ``mmco`` command-line entry point (design spec §7).

``mmco run [sensors.yaml] [--seconds N]`` boots a :class:`~mmco.supervisor.supervisor.Supervisor`,
ticks the session, and finalizes the manifest + log + summary on completion, on Ctrl-C, or on a
control ``stop``. With ``--seconds`` it runs for a bounded time (handy for the demo and tests); with
none it runs **unbounded** until a stop signal (SIGTERM/SIGINT) or ``mmco stop`` (the container mode).
With **no config path** it auto-discovers devices and builds a default session, falling back to the
simulated sensor when nothing runnable is found (spec §7).

A small driver registry maps a config's ``driver`` name to a builder that produces a
:class:`SensorSpec`; its keys are the ``runnable_drivers`` the default-session builder filters to. A
live status table is printed each tick. The output directory defaults from ``MMCO_OUTPUT_DIR`` when
``--output-dir`` is not given, so a container configures the box purely through the environment.
"""

from __future__ import annotations

import argparse
import os
import signal
import threading
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

_TICK_S = 0.05
_STATUS_EVERY_S = 1.0
_OUTPUT_DIR_ENV = "MMCO_OUTPUT_DIR"
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


def _resolve_output_dir(flag: str | None) -> str:
    """Output dir: an explicit ``--output-dir`` wins, else ``MMCO_OUTPUT_DIR``, else the cwd."""
    if flag is not None:
        return flag
    return os.environ.get(_OUTPUT_DIR_ENV) or "."


def _install_signal_handlers(stop_flag: threading.Event) -> None:
    """Make SIGTERM/SIGINT request a graceful stop (so the container finalizes on shutdown)."""
    def _handler(_signum, _frame):
        stop_flag.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass  # not in the main thread, or unsupported on this platform


def run_session(
    config: SessionConfig,
    *,
    max_seconds: float | None = None,
    session_id: str | None = None,
    stop_flag: threading.Event | None = None,
) -> Path:
    """Record a configured session; finalize (manifest + log + summary) and return its directory.

    Runs until ``max_seconds`` elapses (when given), ``stop_flag`` is set (by a signal or a control
    ``stop``), or ``KeyboardInterrupt``. With ``max_seconds=None`` and no stop request it runs
    indefinitely — the container mode.
    """
    session_id = session_id or _new_session_id()
    base_dir = Path(config.output_dir)
    stop_flag = stop_flag if stop_flag is not None else threading.Event()
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
    deadline = None if max_seconds is None else time.monotonic() + max_seconds
    try:
        while not stop_flag.is_set() and (deadline is None or time.monotonic() < deadline):
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
        "--seconds", type=float, default=None,
        help="record for this many seconds (default: run until stopped)",
    )
    run.add_argument(
        "--output-dir", default=None,
        help=f"where to write recordings (default: ${_OUTPUT_DIR_ENV} or the cwd)",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        output_dir = _resolve_output_dir(args.output_dir)
        try:
            config = _resolve_config(args.config, output_dir=output_dir)
        except ConfigError as exc:
            print(f"{exc.code.code} {exc}")
            return 1
        stop_flag = threading.Event()
        _install_signal_handlers(stop_flag)
        sdir = run_session(config, max_seconds=args.seconds, stop_flag=stop_flag)
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

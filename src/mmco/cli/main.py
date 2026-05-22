"""The ``mmco`` command-line entry point (design spec §7).

``mmco run <sensors.yaml> [--seconds N]`` boots a :class:`~mmco.supervisor.supervisor.Supervisor`
from a config file, ticks the session, and finalizes the manifest + log + summary on completion or
on Ctrl-C. The bounded ``--seconds`` makes the command testable and gives the demo a definite end.

A small **simulated-only** driver registry maps a config's ``driver`` name to a builder that
produces a :class:`SensorSpec`. Real drivers ship via an entry-point plugin registry in Phase 8;
this dict is the seam. A live status table is printed each tick (best-effort, added in Task 7.4).

Detached ``mmco stop`` / ``mmco status`` against a separately-running daemon need an IPC channel
(socket/pidfile) that is out of scope this phase; only the in-process ``run`` and the status
*renderer* land here (see the Phase 7 plan's locked decisions).
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from mmco.config.config import ConfigError, SensorConfig, SessionConfig, load_config
from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.paths import session_dir
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.supervisor import SensorSpec, Supervisor

_DEFAULT_SECONDS = 10.0
_TICK_S = 0.05
_N_SLOTS = 16
_SLOT_SIZE = 64


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


# The seam Phase 8 generalizes into an entry-point plugin registry.
_DRIVER_REGISTRY: dict[str, Callable[[SensorConfig], SensorSpec]] = {
    "simulated": _build_simulated,
}


def build_spec(sc: SensorConfig) -> SensorSpec:
    """Resolve a sensor config to a :class:`SensorSpec` via the driver registry."""
    builder = _DRIVER_REGISTRY.get(sc.driver)
    if builder is None:
        raise ConfigError(f"unknown driver {sc.driver!r} for sensor {sc.id!r}")
    return builder(sc)


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
    specs = [build_spec(sc) for sc in config.sensors]
    supervisor = Supervisor(
        session_id=session_id,
        base_dir=base_dir,
        specs=specs,
        policy=RestartPolicy(base_s=0.5, cap_s=5.0),
    )
    supervisor.start()
    try:
        deadline = time.monotonic() + max_seconds
        while time.monotonic() < deadline:
            supervisor.tick()
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
    run = sub.add_parser("run", help="record a session from a config file")
    run.add_argument("config", help="path to sensors.yaml")
    run.add_argument(
        "--seconds", type=float, default=_DEFAULT_SECONDS,
        help="how long to record before finalizing (default: %(default)s)",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"{exc.code.code} {exc}")
            return 1
        sdir = run_session(config, max_seconds=args.seconds)
        print(f"session written to {sdir}")
        return 0
    return 2

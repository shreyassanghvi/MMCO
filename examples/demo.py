#!/usr/bin/env python
"""A narrated, end-to-end demo of MMCO - runs with no hardware and no Docker.

Two hardware-free scenes exercise the whole system, plus optional real-device modes for a Linux box
with a camera attached:

  python examples/demo.py                # both hardware-free scenes (sim + fake webcam)
  python examples/demo.py --discover     # enumerate real capture devices (issue #15)
  python examples/demo.py --webcam -s 8  # record a real USB webcam for 8s (issue #16)

The default mode needs only ``pip install -e .`` - it uses the simulated driver and the webcam's
fake-capture backend, so it shows recording, the live control channel, graceful degradation, and
auto-reconnect on any OS. The real modes need a Linux V4L2 node (a native Ubuntu box; not WSL2,
whose stock kernel has no uvcvideo driver).
"""

from __future__ import annotations

import argparse
import tempfile
import threading
import time
from pathlib import Path

from mmco.cli.main import run_session, runnable_driver_names
from mmco.config.config import SensorConfig, SessionConfig
from mmco.core.capabilities import (
    Capabilities,
    Column,
    StreamType,
    TabularSchema,
    VideoSchema,
)
from mmco.core.manifest import SessionManifest
from mmco.discovery.default_session import build_default_session
from mmco.discovery.discovery import discover_devices
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.drivers.webcam_v4l2 import WebcamConfig, WebcamDriver
from mmco.ipc.client import control_request
from mmco.paths import (
    control_addr_path,
    manifest_path,
    session_dir,
    session_log_path,
    summary_path,
)
from mmco.record.session_log import read_log
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.supervisor import SensorSpec, Supervisor

_W, _H = 64, 48  # tiny synthetic frame keeps the demo fast


# -- narration helpers ------------------------------------------------------
def hr(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


def step(msg: str) -> None:
    print(f"\n-> {msg}")


def show_file(path: Path, label: str, *, max_lines: int | None = None) -> None:
    text = path.read_text()
    lines = text.splitlines()
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(text.splitlines()) - max_lines} more lines)"]
    print(f"\n--- {label}: {path.name} ---")
    print("\n".join(lines))


def show_manifest(sdir: Path) -> SessionManifest:
    manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
    print(f"\n--- manifest.json: {len(manifest.streams)} stream(s) ---")
    for block in manifest.streams:
        off = f", latency_offset={block.latency_offset} ns" if block.latency_offset else ""
        print(f"  {block.sensor_id} ({block.type.name.lower()}){off}")
        for seg in block.segments:
            print(f"    segment[{seg.block_index}]: {seg.file_path}")
        for gap in block.gaps:
            print(f"    GAP {gap.code.code} {gap.code.message}: {gap.reason}")
    return manifest


def list_outputs(sdir: Path) -> None:
    print(f"\n--- files written under {sdir.name}/ ---")
    for p in sorted(sdir.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(sdir)}  ({p.stat().st_size} bytes)")


# -- Scene A: one command, self-documenting + live control channel ----------
def scene_control(workdir: Path) -> None:
    hr("Scene A - one command records a self-documenting session you can control live")
    config = SessionConfig(
        output_dir=str(workdir),
        sensors=[
            SensorConfig(
                id="imu0", driver="simulated", rate_hz=50.0, identity="id-imu0",
                protocol="imu", latency_offset_ns=2_000_000,  # 2 ms declared latency
            ),
            SensorConfig(id="imu1", driver="simulated", rate_hz=50.0, identity="id-imu1"),
        ],
        recording_profiles={"imu": {"format": "parquet"}},
    )
    sid = "demo-control"
    stop = threading.Event()

    step("starting an unbounded `mmco run` session on a background thread (2 simulated sensors)")
    runner = threading.Thread(
        target=lambda: run_session(config, max_seconds=None, stop_flag=stop, session_id=sid)
    )
    runner.start()
    try:
        addr = control_addr_path(session_dir(workdir, sid))
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not addr.exists():
            time.sleep(0.05)

        step("`mmco status` over the loopback control channel (from another shell / docker exec):")
        time.sleep(0.4)
        print(control_request(str(addr), "status")["body"])

        step("`mmco stop` - request a graceful finalize")
        print(control_request(str(addr), "stop"))
    finally:
        stop.set()
        runner.join(timeout=10.0)

    sdir = session_dir(workdir, sid)
    step("the session documented itself - no hand-logging:")
    show_manifest(sdir)
    show_file(summary_path(sdir), "human summary", max_lines=14)


# -- Scene B: graceful degradation + video ----------------------------------
def _sim_spec(sensor_id: str) -> SensorSpec:
    return SensorSpec(
        sensor_id=sensor_id, identity=f"id-{sensor_id}", rate_hz=50.0, n_slots=16, slot_size=64,
        driver_factory=SimulatedDriver,
        driver_config=SimConfig(sensor_id=sensor_id, rate_hz=50.0),
        capabilities=Capabilities(
            type=StreamType.TABULAR, rate=50.0,
            schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
        ),
    )


def _fake_webcam_spec() -> SensorSpec:
    return SensorSpec(
        sensor_id="cam0", identity="usb-fake-cam", rate_hz=30.0,
        n_slots=8, slot_size=_W * _H * 3,
        driver_factory=WebcamDriver,
        driver_config=WebcamConfig(
            sensor_id="cam0", identity="usb-fake-cam", width=_W, height=_H, fps=30.0,
            backend="fake", fake_nodes=("/dev/video0", "/dev/video2"), disconnect_after=8,
        ),
        capabilities=Capabilities(
            type=StreamType.VIDEO, rate=30.0,
            schema=VideoSchema(codec_or_raw="raw", width=_W, height=_H, pixel_format="rgb24"),
        ),
    )


def scene_degradation(workdir: Path) -> None:
    hr("Scene B - a webcam drops mid-session; the box keeps recording and reconnects")
    sid = "demo-degradation"
    supervisor = Supervisor(
        session_id=sid, base_dir=workdir,
        specs=[_sim_spec("imu0"), _fake_webcam_spec()],
        policy=RestartPolicy(base_s=0.05, cap_s=0.3),
    )
    step("recording a simulated IMU + a webcam (mp4); the webcam will 'unplug' after a few frames")
    supervisor.start()
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and supervisor.respawns.get("cam0", 0) < 1:
            supervisor.tick()
            time.sleep(0.02)
        respawns = supervisor.respawns.get("cam0", 0)
        step(f"webcam reconnected by stable identity (respawns={respawns})")
        for _ in range(15):
            supervisor.tick()
            time.sleep(0.02)
    finally:
        supervisor.stop()

    sdir = session_dir(workdir, sid)
    manifest = show_manifest(sdir)
    cam = next(b for b in manifest.streams if b.sensor_id == "cam0")
    step(f"the webcam recorded {len(cam.segments)} mp4 segment(s), gap preserved between them")
    list_outputs(sdir)
    step("the fault is named in plain English, with its code, in the summary:")
    for event in read_log(str(session_log_path(sdir))):
        if event.code is not None:
            print(f"  log: {event.code.code} {event.code.message} (sensor={event.sensor_id})")


# -- real-device modes (Linux + camera) -------------------------------------
def mode_discover() -> None:
    hr("Device discovery (issue #15) - real capture devices with stable identities")
    devices = discover_devices()
    if not devices:
        print("\n(no capture devices found - on WSL2 this is expected: the stock kernel has no")
        print(" V4L2/uvcvideo driver. Run on a native Linux box with a camera/serial device.)")
        return
    for d in devices:
        print(f"  {d.kind.name:<6} node={d.node}  identity={d.identity}  ({d.description})")


def mode_webcam(seconds: float, workdir: Path) -> None:
    hr("Real webcam capture (issue #16) - auto-discover, record, finalize")
    devices = discover_devices()
    config = build_default_session(
        devices, output_dir=str(workdir), runnable_drivers=runnable_driver_names()
    )
    drivers = [s.driver for s in config.sensors]
    step(f"auto-built session drivers: {drivers}")
    if "webcam_v4l2" not in drivers:
        print("\n(no runnable webcam discovered - falling back to simulated. Attach a USB camera")
        print(" on a native Linux host to record real video; unplug mid-run for E004 + reconnect.)")
    sid = "demo-webcam"
    step(f"recording for {seconds:.0f}s - unplug the camera now to see the gap + reconnect")
    run_session(config, max_seconds=seconds, session_id=sid)
    sdir = session_dir(workdir, sid)
    show_manifest(sdir)
    list_outputs(sdir)


def footer() -> None:
    hr("Same thing, one command (no Python needed)")
    print(
        "\n  mmco run                         # auto-discover devices; simulated fallback\n"
        "  mmco run sensors.yaml --seconds 10\n"
        "  mmco status                      # live table from a running session\n"
        "  mmco stop                        # graceful finalize\n"
        "\n  # or fully containerized:\n"
        "  docker compose up --build\n"
        "  docker compose exec mmco mmco status\n"
        "  docker compose exec mmco mmco stop\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MMCO feature demo.")
    parser.add_argument("--discover", action="store_true", help="enumerate real devices (#15)")
    parser.add_argument("--webcam", action="store_true", help="record a real webcam (#16)")
    parser.add_argument(
        "-s", "--seconds", type=float, default=8.0, help="real webcam capture length"
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="mmco-demo-") as tmp:
        workdir = Path(tmp)
        if args.discover:
            mode_discover()
        elif args.webcam:
            mode_webcam(args.seconds, workdir)
        else:
            scene_control(workdir)
            scene_degradation(workdir)
            footer()
    print("\nDemo complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

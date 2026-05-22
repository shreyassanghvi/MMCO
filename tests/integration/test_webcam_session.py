"""End-to-end: simulated + webcam recording together, with a webcam disconnect/reconnect.

Drives the full bus -> recorder -> video writer -> manifest path with the webcam on its **fake
backend** (spawn-safe, no hardware): both streams record, the webcam loses its device (coded E004
gap) while the simulated stream keeps going, and the webcam reconnects into a new segment.
"""

from __future__ import annotations

import time

from mmco.cli.main import runnable_driver_names
from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema, VideoSchema
from mmco.core.errors import ErrorCode
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.drivers.webcam_v4l2 import WebcamConfig, WebcamDriver
from mmco.paths import manifest_path, session_dir, session_log_path, summary_path
from mmco.record.session_log import read_log
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.supervisor import SensorSpec, Supervisor

_W, _H = 64, 48


def _sim_spec() -> SensorSpec:
    return SensorSpec(
        sensor_id="imu0",
        identity="id-imu0",
        rate_hz=50.0,
        n_slots=16,
        slot_size=64,
        driver_factory=SimulatedDriver,
        driver_config=SimConfig(sensor_id="imu0", rate_hz=50.0),
        capabilities=Capabilities(
            type=StreamType.TABULAR,
            rate=50.0,
            schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
        ),
    )


def _webcam_spec() -> SensorSpec:
    return SensorSpec(
        sensor_id="cam0",
        identity="usb-fake-cam",
        rate_hz=30.0,
        n_slots=8,
        slot_size=_W * _H * 3,
        driver_factory=WebcamDriver,
        driver_config=WebcamConfig(
            sensor_id="cam0",
            identity="usb-fake-cam",
            width=_W,
            height=_H,
            fps=30.0,
            backend="fake",
            fake_nodes=("/dev/video0", "/dev/video2"),
            disconnect_after=5,
        ),
        capabilities=Capabilities(
            type=StreamType.VIDEO,
            rate=30.0,
            schema=VideoSchema(codec_or_raw="raw", width=_W, height=_H, pixel_format="rgb24"),
        ),
    )


def test_cli_registry_includes_webcam():
    assert "webcam_v4l2" in runnable_driver_names()


def test_sim_plus_webcam_records_with_disconnect_and_reconnect(tmp_path):
    supervisor = Supervisor(
        session_id="sess-cam",
        base_dir=tmp_path,
        specs=[_sim_spec(), _webcam_spec()],
        policy=RestartPolicy(base_s=0.05, cap_s=0.3),
    )
    supervisor.start()
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and supervisor.respawns.get("cam0", 0) < 1:
            supervisor.tick()
            time.sleep(0.02)
        for _ in range(15):
            supervisor.tick()
            time.sleep(0.02)
    finally:
        supervisor.stop()

    sdir = session_dir(tmp_path, "sess-cam")
    assert manifest_path(sdir).exists()
    assert session_log_path(sdir).exists()
    assert summary_path(sdir).exists()

    # both streams recorded; the webcam produced at least one mp4 segment
    from mmco.core.manifest import SessionManifest

    manifest = SessionManifest.from_json(manifest_path(sdir).read_text())
    by_id = {b.sensor_id: b for b in manifest.streams}
    assert {"imu0", "cam0"} <= set(by_id)
    cam_files = [sdir / seg.file_path for seg in by_id["cam0"].segments]
    assert any(f.suffix == ".mp4" and f.exists() for f in cam_files)

    # the webcam disconnect was logged with its code, and it reconnected
    events = read_log(str(session_log_path(sdir)))
    assert any(e.code is ErrorCode.DEVICE_DISCONNECTED for e in events)
    assert supervisor.respawns.get("cam0", 0) >= 1

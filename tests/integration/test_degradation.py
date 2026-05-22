"""End-to-end resilience: a sensor disconnects mid-session; the box keeps recording and reconnects.

Exercises the device-gone (E004) path through the full supervisor → host → recorder → manifest
chain, with no hardware. Complements the supervisor's crash (E002) test by checking the disconnect
code path.
"""

import time
from pathlib import Path

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.errors import ErrorCode
from mmco.core.manifest import SessionManifest
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.supervisor import SensorSpec, Supervisor


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=50.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


def _spec(sensor_id: str, identity: str, failure: str | None) -> SensorSpec:
    return SensorSpec(
        sensor_id=sensor_id,
        identity=identity,
        rate_hz=50.0,
        n_slots=16,
        slot_size=64,
        driver_factory=SimulatedDriver,
        driver_config=SimConfig(
            sensor_id=sensor_id, rate_hz=50.0, failure=failure, failure_after=3
        ),
        capabilities=_caps(),
    )


def test_disconnect_mid_session_keeps_recording_and_reconnects(tmp_path):
    supervisor = Supervisor(
        session_id="sess-disc",
        base_dir=tmp_path,
        specs=[
            _spec("steady0", "id-steady", failure=None),
            _spec("flaky0", "id-flaky", failure="disconnect"),
        ],
        policy=RestartPolicy(base_s=0.05, cap_s=0.3),
    )
    supervisor.start()
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and supervisor.respawns.get("flaky0", 0) < 1:
            supervisor.tick()
            time.sleep(0.02)
        for _ in range(25):
            supervisor.tick()
            time.sleep(0.02)
    finally:
        manifest_file = supervisor.stop()

    assert supervisor.alive_sensors() == []

    manifest = SessionManifest.from_json(Path(manifest_file).read_text())
    blocks = {b.sensor_id: b for b in manifest.streams}

    # the steady stream is never interrupted
    assert blocks["steady0"].gaps == ()
    assert len(blocks["steady0"].segments) >= 1

    # the flaky stream records a device-disconnect gap and resumes into a new segment
    flaky = blocks["flaky0"]
    assert any(g.code is ErrorCode.DEVICE_DISCONNECTED for g in flaky.gaps)
    assert len(flaky.segments) >= 2

    # the session log tells the story: a device-gone code and a reconnect
    assert any(e.code is ErrorCode.DEVICE_DISCONNECTED for e in supervisor.aggregated_logs)
    assert any("reconnect" in e.message.lower() for e in supervisor.aggregated_logs)

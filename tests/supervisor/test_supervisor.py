import sys
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


def test_one_stream_crashes_and_recovers_while_the_other_keeps_recording(tmp_path):
    supervisor = Supervisor(
        session_id="sess-deg",
        base_dir=tmp_path,
        specs=[
            _spec("good0", "id-good", failure=None),
            _spec("bad0", "id-bad", failure="crash"),
        ],
        policy=RestartPolicy(base_s=0.05, cap_s=0.3),
    )
    supervisor.start()
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and supervisor.respawns.get("bad0", 0) < 2:
            supervisor.tick()
            time.sleep(0.02)
        for _ in range(25):  # let post-respawn events land
            supervisor.tick()
            time.sleep(0.02)
    finally:
        manifest_file = supervisor.stop()

    assert supervisor.alive_sensors() == []  # no leaked child processes

    manifest = SessionManifest.from_json(Path(manifest_file).read_text())
    blocks = {b.sensor_id: b for b in manifest.streams}

    good = blocks["good0"]
    assert len(good.segments) >= 1
    assert good.gaps == ()  # never interrupted

    bad = blocks["bad0"]
    assert any(g.code is ErrorCode.DRIVER_CRASH for g in bad.gaps)
    assert len(bad.segments) >= 2  # resumed into new segments after re-spawn

    assert any(e.code is ErrorCode.DRIVER_CRASH for e in supervisor.aggregated_logs)
    assert any("reconnect" in e.message.lower() for e in supervisor.aggregated_logs)


def test_no_leaked_shared_memory_segments(tmp_path):
    if sys.platform == "win32":
        import pytest

        pytest.skip("POSIX /dev/shm semantics")
    from mmco.bus.ring import sweep_stale_segments

    supervisor = Supervisor(
        session_id="sess-leak",
        base_dir=tmp_path,
        specs=[_spec("good0", "id-good", failure=None)],
        policy=RestartPolicy(base_s=0.05, cap_s=0.3),
    )
    supervisor.start()
    for _ in range(10):
        supervisor.tick()
        time.sleep(0.02)
    supervisor.stop()
    assert sweep_stale_segments() == []  # supervisor unlinked everything it created

"""End-to-end: a session documents itself — manifest + log + summary, with no hand-logging.

Runs a supervised session with a sensor that disconnects, then asserts all three artifacts exist and
that the summary names the fault in plain English with its error code.
"""

import time

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.errors import ErrorCode
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.paths import manifest_path, session_dir, session_log_path, summary_path
from mmco.record.session_log import read_log
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


def test_session_produces_manifest_log_and_summary(tmp_path):
    supervisor = Supervisor(
        session_id="sess-doc",
        base_dir=tmp_path,
        specs=[_spec("flaky0", "id-flaky", failure="disconnect")],
        policy=RestartPolicy(base_s=0.05, cap_s=0.3),
    )
    supervisor.start()
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and supervisor.respawns.get("flaky0", 0) < 1:
            supervisor.tick()
            time.sleep(0.02)
        for _ in range(15):
            supervisor.tick()
            time.sleep(0.02)
    finally:
        supervisor.stop()

    sdir = session_dir(tmp_path, "sess-doc")
    assert manifest_path(sdir).exists()
    assert session_log_path(sdir).exists()
    assert summary_path(sdir).exists()

    # the log re-reads with the fault code present
    events = read_log(str(session_log_path(sdir)))
    assert any(e.code is ErrorCode.DEVICE_DISCONNECTED for e in events)

    # the summary names the fault in plain English with its code
    summary_text = summary_path(sdir).read_text()
    assert "MMCO-E004" in summary_text
    assert "device disconnected" in summary_text

"""Tests for the live status renderer and Supervisor.snapshot() (Task 7.4)."""

from __future__ import annotations

import time

from mmco.cli.status_view import render_status
from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.errors import ErrorCode
from mmco.drivers.simulated import SimConfig, SimulatedDriver
from mmco.supervisor.policy import RestartPolicy
from mmco.supervisor.supervisor import SensorSpec, Supervisor


def test_render_status_includes_sensors_counts_and_codes():
    snapshot = [
        {"sensor_id": "cam0", "alive": True, "dropped": 0, "reconnects": 0, "last_code": None},
        {
            "sensor_id": "imu0",
            "alive": False,
            "dropped": 7,
            "reconnects": 2,
            "last_code": ErrorCode.DEVICE_DISCONNECTED,
        },
    ]

    text = render_status(snapshot)

    assert "cam0" in text
    assert "imu0" in text
    assert "7" in text  # dropped count
    assert "2" in text  # reconnect count
    assert "MMCO-E004" in text  # last error code


def test_render_status_empty_snapshot_renders_header():
    text = render_status([])
    assert text.strip() != ""  # a header still renders, no exception


def _spec(sensor_id: str) -> SensorSpec:
    return SensorSpec(
        sensor_id=sensor_id,
        identity=f"id-{sensor_id}",
        rate_hz=50.0,
        n_slots=16,
        slot_size=64,
        driver_factory=SimulatedDriver,
        driver_config=SimConfig(sensor_id=sensor_id, rate_hz=50.0),
        capabilities=Capabilities(
            type=StreamType.TABULAR,
            rate=50.0,
            schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
        ),
    )


def test_supervisor_snapshot_lists_every_sensor(tmp_path):
    supervisor = Supervisor(
        session_id="sess-snap",
        base_dir=tmp_path,
        specs=[_spec("a0"), _spec("b0")],
        policy=RestartPolicy(base_s=0.5, cap_s=5.0),
    )
    supervisor.start()
    try:
        time.sleep(0.1)
        supervisor.tick()
        snapshot = supervisor.snapshot()
    finally:
        supervisor.stop()

    assert {row["sensor_id"] for row in snapshot} == {"a0", "b0"}
    for row in snapshot:
        assert set(row) == {"sensor_id", "alive", "dropped", "reconnects", "last_code"}

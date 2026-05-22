"""Out-of-box: with no config and no hardware, the box still records (Task 8.4).

Drives the auto-discovery path with discovery injected empty (as on a bare CI box), builds the
default session, and asserts it falls back to the simulated sensor and finalizes all artifacts.
"""

from __future__ import annotations

from mmco.cli.main import run_session, runnable_driver_names
from mmco.discovery.default_session import build_default_session
from mmco.paths import manifest_path, session_log_path, summary_path


def test_out_of_box_empty_discovery_records_via_simulated(tmp_path):
    devices = []  # injected empty discovery — no hardware present

    config = build_default_session(
        devices, output_dir=str(tmp_path), runnable_drivers=runnable_driver_names()
    )
    assert [s.driver for s in config.sensors] == ["simulated"]

    sdir = run_session(config, max_seconds=1.0, session_id="sess-oob")

    assert manifest_path(sdir).exists()
    assert session_log_path(sdir).exists()
    assert summary_path(sdir).exists()

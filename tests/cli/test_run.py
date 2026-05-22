"""Tests for the `mmco run` CLI: record a configured session end-to-end (Task 7.3)."""

from __future__ import annotations

from mmco.cli.main import main, run_session
from mmco.config.config import load_config
from mmco.paths import manifest_path, session_log_path, summary_path


def _write_config(tmp_path):
    cfg = tmp_path / "sensors.yaml"
    cfg.write_text(
        f"output_dir: {tmp_path.as_posix()}\n"
        "sensors:\n"
        "  - id: sim0\n"
        "    driver: simulated\n"
        "    identity: id-sim0\n"
        "    rate_hz: 50.0\n"
    )
    return cfg


def test_run_session_finalizes_all_artifacts(tmp_path):
    config = load_config(str(_write_config(tmp_path)))

    sdir = run_session(config, max_seconds=1.0, session_id="sess-cli")

    assert manifest_path(sdir).exists()
    assert session_log_path(sdir).exists()
    assert summary_path(sdir).exists()


def test_main_run_returns_zero(tmp_path):
    cfg = _write_config(tmp_path)
    assert main(["run", str(cfg), "--seconds", "1"]) == 0

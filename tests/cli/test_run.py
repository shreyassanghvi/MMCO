"""Tests for the `mmco run` CLI: record a configured session end-to-end (Task 7.3, 10.1)."""

from __future__ import annotations

import threading

from mmco.cli.main import _resolve_output_dir, main, run_session
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


def test_main_run_no_config_auto_discovers(tmp_path):
    # No config path → discovery (empty on the dev box) → simulated fallback → records cleanly.
    assert main(["run", "--seconds", "1", "--output-dir", str(tmp_path)]) == 0


def test_output_dir_falls_back_to_env(monkeypatch):
    monkeypatch.delenv("MMCO_OUTPUT_DIR", raising=False)
    assert _resolve_output_dir(None) == "."
    monkeypatch.setenv("MMCO_OUTPUT_DIR", "/data")
    assert _resolve_output_dir(None) == "/data"
    assert _resolve_output_dir("/explicit") == "/explicit"  # explicit flag wins over env


def test_unbounded_run_finalizes_when_stop_flag_set(tmp_path):
    config = load_config(str(_write_config(tmp_path)))
    stop = threading.Event()
    threading.Timer(0.8, stop.set).start()

    sdir = run_session(
        config, max_seconds=None, stop_flag=stop, session_id="sess-unbounded"
    )

    assert stop.is_set()
    assert manifest_path(sdir).exists()
    assert session_log_path(sdir).exists()
    assert summary_path(sdir).exists()

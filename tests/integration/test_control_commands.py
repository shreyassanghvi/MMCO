"""Integration: detached `mmco status` / `mmco stop` against a running session (Task 10.3)."""

from __future__ import annotations

import threading
import time

from mmco.cli.main import main, run_session
from mmco.config.config import load_config
from mmco.paths import (
    control_addr_path,
    manifest_path,
    session_dir,
    session_log_path,
    summary_path,
)

_SESSION_ID = "sess-ctl"


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


def test_status_then_stop_against_running_session(tmp_path, capsys):
    config = load_config(str(_write_config(tmp_path)))
    stop = threading.Event()
    result: dict = {}

    def _run():
        result["sdir"] = run_session(
            config, max_seconds=None, stop_flag=stop, session_id=_SESSION_ID
        )

    runner = threading.Thread(target=_run)
    runner.start()
    try:
        addr = control_addr_path(session_dir(tmp_path, _SESSION_ID))
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not addr.exists():
            time.sleep(0.02)
        assert addr.exists(), "control channel never came up"

        # detached status prints the live table for the running sensor
        assert main(["status", "--output-dir", str(tmp_path)]) == 0
        assert "sim0" in capsys.readouterr().out

        # detached stop finalizes the session and the run thread exits
        assert main(["stop", "--output-dir", str(tmp_path)]) == 0
    finally:
        stop.set()  # safety net if stop command failed
        runner.join(timeout=10.0)

    assert not runner.is_alive()
    sdir = result["sdir"]
    assert manifest_path(sdir).exists()
    assert session_log_path(sdir).exists()
    assert summary_path(sdir).exists()


def test_status_with_no_running_session_returns_error(tmp_path):
    assert main(["status", "--output-dir", str(tmp_path)]) == 1

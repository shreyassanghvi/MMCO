"""Tests for the control client and session-address discovery (Task 10.3)."""

from __future__ import annotations

import os
import threading

import pytest

from mmco.ipc.client import control_request, find_session_addr
from mmco.ipc.server import ControlServer
from mmco.paths import recordings_root


def test_control_request_round_trips_status_and_stop(tmp_path):
    snapshot = [
        {"sensor_id": "imu0", "alive": True, "dropped": 0, "reconnects": 0, "last_code": None}
    ]
    stop = threading.Event()
    addr = tmp_path / "control.addr"
    server = ControlServer(
        snapshot=lambda: snapshot, request_stop=stop.set, addr_path=str(addr)
    )
    server.start()
    try:
        status = control_request(str(addr), "status")
        ack = control_request(str(addr), "stop")
    finally:
        server.close()

    assert status["ok"] is True and "imu0" in status["body"]
    assert ack["ok"] is True and stop.is_set()


def test_find_session_addr_picks_newest(tmp_path):
    root = recordings_root(tmp_path)
    older = root / "sess-old"
    newer = root / "sess-new"
    for d in (older, newer):
        d.mkdir(parents=True)
    (older / "control.addr").write_text("11111")
    (newer / "control.addr").write_text("22222")
    os.utime(older / "control.addr", (1000, 1000))
    os.utime(newer / "control.addr", (2000, 2000))  # newer mtime wins

    found = find_session_addr(str(tmp_path))
    assert found.read_text() == "22222"


def test_find_session_addr_raises_when_none(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_session_addr(str(tmp_path))

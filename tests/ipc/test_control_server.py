"""Tests for the loopback control server (Task 10.2)."""

from __future__ import annotations

import json
import socket
import threading

from mmco.ipc.server import ControlServer


def _request(addr_path, payload: dict) -> dict:
    port = int(addr_path.read_text().strip())
    with socket.create_connection(("127.0.0.1", port), timeout=2.0) as sock:
        sock.sendall((json.dumps(payload) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode())


def _server(tmp_path, snapshot, stop_event):
    return ControlServer(
        snapshot=lambda: snapshot,
        request_stop=stop_event.set,
        addr_path=str(tmp_path / "control.addr"),
    )


def test_status_returns_rendered_table(tmp_path):
    snapshot = [
        {"sensor_id": "cam0", "alive": True, "dropped": 0, "reconnects": 0, "last_code": None}
    ]
    stop = threading.Event()
    server = _server(tmp_path, snapshot, stop)
    server.start()
    try:
        resp = _request(tmp_path / "control.addr", {"cmd": "status"})
    finally:
        server.close()

    assert resp["ok"] is True
    assert "cam0" in resp["body"]


def test_stop_invokes_request_stop_and_acks(tmp_path):
    stop = threading.Event()
    server = _server(tmp_path, [], stop)
    server.start()
    try:
        resp = _request(tmp_path / "control.addr", {"cmd": "stop"})
    finally:
        server.close()

    assert resp["ok"] is True
    assert stop.is_set()


def test_unknown_command_returns_not_ok_without_crashing(tmp_path):
    stop = threading.Event()
    server = _server(tmp_path, [], stop)
    server.start()
    try:
        resp = _request(tmp_path / "control.addr", {"cmd": "frobnicate"})
        # server is still alive and answers a follow-up
        follow = _request(tmp_path / "control.addr", {"cmd": "status"})
    finally:
        server.close()

    assert resp["ok"] is False
    assert follow["ok"] is True


def test_addr_file_present_while_serving_and_gone_after_close(tmp_path):
    addr = tmp_path / "control.addr"
    stop = threading.Event()
    server = _server(tmp_path, [], stop)
    server.start()
    assert addr.exists()
    server.close()
    assert not addr.exists()

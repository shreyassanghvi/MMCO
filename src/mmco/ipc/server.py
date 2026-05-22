"""Loopback control server — the in-session IPC daemon (design spec §7).

A running ``mmco run`` session hosts a :class:`ControlServer` in a background thread so a detached
operator (or ``docker exec``) can ask it for live status or tell it to stop. There is no separate
daemon process: the session *is* the server.

Transport is a **TCP socket bound to 127.0.0.1** on an ephemeral port written to ``control.addr`` in
the session directory; clients read that file to connect. Loopback-only by construction (no port is
exposed beyond the host/container), so this is not a network service. The wire protocol is one
line-delimited JSON request per connection -> one JSON response:

- ``{"cmd": "status"}`` -> ``{"ok": true, "body": "<rendered status table>"}``
- ``{"cmd": "stop"}``   -> ``{"ok": true, "stopping": true}`` (and the session's stop is requested)
- anything else         -> ``{"ok": false, "error": "..."}``
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from pathlib import Path

from mmco.cli.status_view import render_status

_HOST = "127.0.0.1"
_ACCEPT_TIMEOUT_S = 0.2  # so the serve loop can notice shutdown promptly


class ControlServer:
    """Serves ``status``/``stop`` over a loopback TCP socket for one session's lifetime."""

    def __init__(
        self,
        *,
        snapshot: Callable[[], list[dict]],
        request_stop: Callable[[], None],
        addr_path: str,
    ):
        self._snapshot = snapshot
        self._request_stop = request_stop
        self._addr_path = Path(addr_path)
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._shutdown = threading.Event()

    def start(self) -> None:
        """Bind the loopback socket, publish ``control.addr``, and serve in a daemon thread."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((_HOST, 0))
        self._sock.listen(8)
        self._sock.settimeout(_ACCEPT_TIMEOUT_S)
        port = self._sock.getsockname()[1]
        self._addr_path.write_text(str(port))
        self._thread = threading.Thread(target=self._serve, name="mmco-control", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._shutdown.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break  # socket closed during shutdown
            with conn:
                self._handle(conn)

    def _handle(self, conn: socket.socket) -> None:
        try:
            request = self._read_line(conn)
            response = self._dispatch(request)
        except Exception as exc:  # never let one bad client take the server down
            response = {"ok": False, "error": str(exc)}
        conn.sendall((json.dumps(response) + "\n").encode())

    @staticmethod
    def _read_line(conn: socket.socket) -> dict:
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode() or "{}")

    def _dispatch(self, request: dict) -> dict:
        cmd = request.get("cmd")
        if cmd == "status":
            return {"ok": True, "body": render_status(self._snapshot())}
        if cmd == "stop":
            self._request_stop()
            return {"ok": True, "stopping": True}
        return {"ok": False, "error": f"unknown command {cmd!r}"}

    def close(self) -> None:
        """Stop serving, close the socket, and remove ``control.addr``."""
        self._shutdown.set()
        if self._sock is not None:
            self._sock.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._addr_path.unlink(missing_ok=True)

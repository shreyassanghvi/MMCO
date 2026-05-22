"""Control client — talk to a running session's control server (design spec §7).

A short-lived helper used by ``mmco status`` / ``mmco stop``: it reads the session's
``control.addr`` to find the loopback port, sends one line-delimited JSON command, and returns the
JSON response.
:func:`find_session_addr` locates the running session — the newest ``control.addr`` under the output
directory's recordings root, or an explicit ``session_dir``.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

from mmco.paths import control_addr_path, recordings_root

_CONNECT_TIMEOUT_S = 2.0


def control_request(addr_path: str, cmd: str) -> dict:
    """Send ``{"cmd": cmd}`` to the server addressed by ``addr_path`` and return its response."""
    port = int(Path(addr_path).read_text().strip())
    with socket.create_connection(("127.0.0.1", port), timeout=_CONNECT_TIMEOUT_S) as sock:
        sock.sendall((json.dumps({"cmd": cmd}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode())


def find_session_addr(output_dir: str, *, session_dir: str | None = None) -> Path:
    """Locate a running session's ``control.addr`` (explicit ``session_dir`` or the newest one)."""
    if session_dir is not None:
        addr = control_addr_path(Path(session_dir))
        if not addr.exists():
            raise FileNotFoundError(f"no control channel at {addr}")
        return addr
    root = recordings_root(Path(output_dir))
    candidates = sorted(
        root.glob(f"*/{control_addr_path(Path()).name}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no running session under {root}")
    return candidates[0]

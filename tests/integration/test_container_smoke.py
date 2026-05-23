"""Container smoke tests (Task 10.5).

Two levels, both gated on what's available:
- the compose file validates wherever the Docker **CLI** is present (no daemon needed);
- a full build + run requires a reachable Docker **daemon**, so it skips on a box without one
  (e.g. the Windows dev box when Docker Desktop is stopped) and runs on Linux/CI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _docker_cli() -> bool:
    return shutil.which("docker") is not None


def _docker_daemon() -> bool:
    if not _docker_cli():
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=15
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.skipif(not _docker_cli(), reason="Docker CLI not installed")
def test_compose_file_is_valid():
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=_REPO_ROOT,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.skipif(not _docker_daemon(), reason="Docker daemon not reachable")
def test_container_records_via_sim_fallback(tmp_path):
    subprocess.run(
        ["docker", "build", "-t", "mmco:smoke", "."],
        cwd=_REPO_ROOT,
        check=True,
        timeout=600,
    )
    # No devices mapped -> auto-discovery falls back to the simulated sensor and records.
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-e", "MMCO_OUTPUT_DIR=/data",
            "-v", f"{tmp_path}:/data",
            "mmco:smoke",
            "--seconds", "3",
        ],
        check=True,
        timeout=120,
    )
    manifests = list((tmp_path / "recordings").glob("*/manifest.json"))
    assert manifests, "no recording produced on the host volume"
    session = manifests[0].parent
    assert (session / "session.log.jsonl").exists()
    assert (session / "summary.md").exists()

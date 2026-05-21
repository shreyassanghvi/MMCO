"""Canonical on-disk layout for a captured session.

Layout (design spec §5)::

    <base>/recordings/<session_id>/
        manifest.json        — alignment contract the ML loader reads
        session.log.jsonl    — structured per-event log
        summary.md           — human-readable session summary

Pure path construction: nothing here touches the filesystem. Session-id generation and directory
creation live where sessions actually start (Phase 4/7), not here.
"""

from __future__ import annotations

from pathlib import Path

RECORDINGS_DIRNAME = "recordings"
MANIFEST_FILENAME = "manifest.json"
SESSION_LOG_FILENAME = "session.log.jsonl"
SUMMARY_FILENAME = "summary.md"


def recordings_root(base: Path) -> Path:
    """Return the recordings root under ``base``."""
    return base / RECORDINGS_DIRNAME


def session_dir(base: Path, session_id: str) -> Path:
    """Return the directory holding a single session's artifacts."""
    return recordings_root(base) / session_id


def manifest_path(session_dir: Path) -> Path:
    """Return the manifest path inside ``session_dir``."""
    return session_dir / MANIFEST_FILENAME


def session_log_path(session_dir: Path) -> Path:
    """Return the structured-log path inside ``session_dir``."""
    return session_dir / SESSION_LOG_FILENAME


def summary_path(session_dir: Path) -> Path:
    """Return the summary path inside ``session_dir``."""
    return session_dir / SUMMARY_FILENAME

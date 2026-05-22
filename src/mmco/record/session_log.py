"""The session log: a JSONL record of everything that happened (design spec §6).

The supervisor aggregates every component's ``LogEvent`` — lifecycle, drops, gaps, reconnects,
errors with codes — over a session. This module persists that list to ``session.log.jsonl`` (one
event per line, in order) and reads it back, so the summary generator and a human (or an ML
pipeline) can replay exactly what occurred.
"""

from __future__ import annotations

from pathlib import Path

from mmco.core.logevent import LogEvent


def write_log(path: str, events: list[LogEvent]) -> None:
    """Write ``events`` to ``path`` as JSONL, one record per line, in order."""
    Path(path).write_text("".join(event.to_json() + "\n" for event in events))


def read_log(path: str) -> list[LogEvent]:
    """Parse a ``session.log.jsonl`` file back into a list of ``LogEvent``s."""
    text = Path(path).read_text()
    return [LogEvent.from_json(line) for line in text.splitlines() if line.strip()]

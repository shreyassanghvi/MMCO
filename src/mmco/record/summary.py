"""Human-readable session summary (design spec §6).

``render_summary`` turns a :class:`~mmco.core.manifest.SessionManifest` plus the session's
``LogEvent``s into a markdown report a scientist can read at a glance: what was captured, for how
long, and — in plain English with its ``MMCO-Exxx`` code — anything that went wrong.

It is built purely from the manifest and the log (no hardware, no reading the data files), so the
sample counts it shows are **approximate** (span x nominal rate), labelled as such. Strict
cross-stream alignment validation lands with the webcam slice (Phase 9); here the clock anchor is
reported.
"""

from __future__ import annotations

from pathlib import Path

from mmco.core.logevent import LogEvent
from mmco.core.manifest import SessionManifest, StreamBlock
from mmco.paths import MANIFEST_FILENAME, SESSION_LOG_FILENAME, SUMMARY_FILENAME
from mmco.record.session_log import read_log


def _span_ns(block: StreamBlock) -> int:
    if not block.segments:
        return 0
    return block.segments[-1].end_timestamp - block.segments[0].start_timestamp


def _stream_section(block: StreamBlock) -> list[str]:
    span = _span_ns(block)
    span_s = span / 1e9
    rate = block.capabilities.rate
    approx = int(span_s * rate) if rate else None
    lines = [
        f"## {block.sensor_id} ({block.type.name.lower()})",
        "",
        f"- Nominal rate: {rate} Hz" if rate else "- Nominal rate: n/a",
        f"- Segments: {len(block.segments)}",
        f"- Captured span: {span_s:.3f} s",
        (f"- Approx samples: ~{approx} (span x rate)" if approx is not None
         else "- Approx samples: n/a"),
        f"- Dropped events: {block.dropped}",
    ]
    if block.gaps:
        lines.append("- Gaps:")
        for gap in block.gaps:
            lines.append(
                f"  - {gap.code.code} {gap.code.message}: {gap.reason} "
                f"(from {gap.start} to {gap.end})"
            )
    else:
        lines.append("- Gaps: none")
    lines.append("")
    return lines


def render_summary(manifest: SessionManifest, events: list[LogEvent]) -> str:
    """Render a markdown summary of a session from its manifest and log events."""
    error_count = sum(1 for e in events if e.code is not None)
    lines = [
        f"# MMCO Session Summary - {manifest.session_id}",
        "",
        f"- Output: {manifest.output_dir}",
        f"- Clock anchor: monotonic {manifest.anchor.monotonic_ns} ns / "
        f"wall {manifest.anchor.wall_ns} ns",
        f"- Streams: {len(manifest.streams)}",
        f"- Coded log events: {error_count}",
        "",
        "_Sample counts are approximate (span x nominal rate). Strict cross-stream "
        "alignment validation arrives with the webcam slice (Phase 9)._",
        "",
    ]
    for block in manifest.streams:
        lines.extend(_stream_section(block))
    return "\n".join(lines)


def write_summary(session_dir: Path) -> Path:
    """Read the manifest + session log from ``session_dir`` and write ``summary.md``."""
    manifest = SessionManifest.from_json((session_dir / MANIFEST_FILENAME).read_text())
    log_path = session_dir / SESSION_LOG_FILENAME
    events = read_log(str(log_path)) if log_path.exists() else []
    out = session_dir / SUMMARY_FILENAME
    out.write_text(render_summary(manifest, events))
    return out

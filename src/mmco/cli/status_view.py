"""Live per-sensor status table (design spec §7).

:func:`render_status` turns a :meth:`Supervisor.snapshot` — a list of per-sensor counter dicts —
into a readable fixed-width text table (sensor, alive, dropped, reconnects, last error code). It is
pure: it touches no supervisor state, so it is trivial to unit-test and safe to print on every tick.
"""

from __future__ import annotations

from mmco.core.errors import ErrorCode

_HEADERS = ("sensor", "alive", "dropped", "reconnects", "last_code")


def _code_str(code: ErrorCode | None) -> str:
    return code.code if code is not None else "-"


def render_status(snapshot: list[dict]) -> str:
    """Render a snapshot as a fixed-width text table; an empty snapshot still shows the header."""
    rows = [
        (
            str(row["sensor_id"]),
            "yes" if row["alive"] else "no",
            str(row["dropped"]),
            str(row["reconnects"]),
            _code_str(row["last_code"]),
        )
        for row in snapshot
    ]
    widths = [
        max(len(_HEADERS[i]), *(len(r[i]) for r in rows)) if rows else len(_HEADERS[i])
        for i in range(len(_HEADERS))
    ]

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [_line(_HEADERS), _line(tuple("-" * w for w in widths))]
    lines.extend(_line(r) for r in rows)
    return "\n".join(lines)

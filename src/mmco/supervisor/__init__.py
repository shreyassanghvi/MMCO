"""The supervisor: lifecycle, health, graceful degradation, and auto-reconnect.

The supervisor spawns one driver host per sensor, owns the shared-memory rings, drains the bus into
the recorder, and watches each stream's health. When a sensor crashes, hangs, or vanishes it opens a
coded gap, keeps the other streams recording, and re-spawns the dead host (by stable identity) so it
resumes into a new segment — the core never goes down with a single stream.
"""

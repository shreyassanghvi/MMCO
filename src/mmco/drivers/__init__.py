"""Bundled sensor drivers.

Phase 3 ships the :mod:`~mmco.drivers.simulated` driver — a deterministic, hardware-free stream that
doubles as the primary test fixture (with injectable failure modes for the degradation tests). Real
drivers (USB webcam, mic, serial IMU) are added in later phases.
"""

# MMCO v1.0.0 — first release

**Multimodal Capture-box Orchestrator** — a software backbone that runs on a capture box and
coordinates whatever sensors are plugged in (USB cameras, mics, serial IMUs, instrument logs). A
wet-lab analog to ROS 2 / NVIDIA Holoscan: a plugin architecture for sensor drivers, a unified
timestamped event bus, configurable per-protocol recording profiles, and graceful degradation when a
sensor drops out — shipped as a containerized service.

Built as an engineering demo for **Transfyr Bio**. The goal: less time documenting and debugging,
more time exploring — auto-detected sensors, one-command capture, and an auto-generated, time-aligned
manifest that *is* the documentation.

## Highlights

- **One command to record.** `docker compose up` (or `mmco run`) auto-detects devices, builds a
  session, and records. With nothing plugged in it falls back to a **simulated sensor**, so a fresh
  clone always produces a recording.
- **Self-documenting sessions.** Every run writes `manifest.json` (the alignment contract an ML loader
  reads), per-stream native files, a structured `session.log.jsonl`, and a human-readable
  `summary.md` — no hand-logging.
- **Keeps recording when a cable drops.** A watchdog detects crashes/hangs/disconnects, logs a coded
  gap (`MMCO-Exxx`), keeps the other streams alive, and auto-reconnects the failed sensor **by stable
  identity** into a new segment. The summary names the fault in plain English.
- **Time alignment.** Single monotonic clock, per-stream constant latency-offset correction, and
  per-frame/per-row timestamp sidecars; cross-stream alignment validated within **±2 ms**.
- **Detached control.** A running session hosts a loopback control channel: `mmco status` (live
  per-sensor table) and `mmco stop` (graceful finalize) work from another shell or `docker exec` —
  including on a detached container.

## What's included

- **Core:** process-per-sensor architecture, shared-memory ring buffer + metadata queue, sensor-driver
  plugin contract, monotonic clock + offset registry, `MMCO-E001…E007` error taxonomy.
- **Drivers:** deterministic **simulated** sensor (with injectable crash/hang/slow/disconnect faults)
  and a **USB webcam (V4L2)** driver bound by stable identity.
- **Recording:** parquet writer (tabular) and **PyAV/ffmpeg** mp4 video writer with a per-frame
  timestamp sidecar; segments + gaps in the manifest; configurable recording profiles (e.g. webcam
  `crf` override).
- **Control surface:** `sensors.yaml` config, `mmco run` / `status` / `stop`, live status table.
- **Container:** `python:3.14-slim` image (non-root), `docker-compose.yml` with a host volume for
  `recordings/` and documented device passthrough.

## Quick start

```
docker compose up --build              # records to ./recordings; Ctrl-C or `down` to stop
docker compose exec mmco mmco status   # live per-sensor table
docker compose exec mmco mmco stop     # graceful finalize
```

Local dev: `pip install -e ".[dev]"` then `mmco run`.

## Quality

- **139 tests** (TDD throughout); test-first, always-green CI path with no hardware required (fakes for
  V4L2 and injectable enumerators).
- Live-validated: container build + record + detached `status`/`stop` end to end.
- Python 3.14; dependencies: `pyarrow`, `PyYAML`, `av`, `numpy`.

## Known follow-ups (not blocking)

- **Linux/WSL2 multiprocessing** validation (dev was on Windows; `spawn` vs `fork` context mixing).
- **Real device enumerators** and the **webcam V4L2 backend** validated on hardware — see
  `docs/hardware-checklist.md` (USB-to-WSL2 needs `usbipd-win`).

## Out of scope (future work)

Mic / serial / IP-camera / logfile drivers, MCAP export, ROS 2 bridge, native (Rust/C++) hot paths,
and latency-offset auto-calibration.

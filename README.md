# MMCO — Multimodal Capture-box Orchestrator

A software backbone that runs on a capture box and coordinates whatever sensors are plugged in (USB
cameras, USB mics, IP cameras, serial IMUs, instrument log files). A wet-lab analog to ROS 2 /
NVIDIA Holoscan: a plugin architecture for sensor drivers, a unified timestamped event bus,
configurable recording profiles per protocol, and graceful degradation when a sensor drops out. Ships
as a containerized service.

**Why it matters:** tools that help scientists spend less time documenting and debugging, and more
time doing the exploration they love — auto-detected sensors, one-command capture, an auto-generated
time-aligned manifest that *is* the documentation, and recordings that keep going when a cable drops.

> Built as an engineering demo for [Transfyr Bio](https://transfyr.ai/).

---

## Status

**Current stage:** Phase 10 complete — all phases done. MMCO ships as a containerized service.
**Active branch:** `impl/phase-10-containerization` (off `master`).
**Last updated:** 2026-05-23.

### One command (container)

```
docker compose up --build        # records to ./recordings on the host; Ctrl-C / `down` to stop
docker compose exec mmco mmco status   # live per-sensor table from the running session
docker compose exec mmco mmco stop     # graceful finalize (manifest + log + summary)
```

With no devices mapped the container records via the **simulated fallback**, so a fresh clone always
produces a recording. Map real capture devices (and find their stable identities) per the device
passthrough block in [`docker-compose.yml`](docker-compose.yml) and
[`docs/hardware-checklist.md`](docs/hardware-checklist.md).

### Local (dev)

`python -m pip install -e ".[dev]"` then `python -m pytest` — 138 passing (3 skipped: POSIX-only
shared-memory sweep tests + the Docker-daemon-gated container smoke test, skipped on Windows). Then
`mmco run` (no config) auto-discovers plugged-in devices — a USB webcam records to `mp4` (with a
per-frame timestamp sidecar) alongside tabular streams — and **falls back to the simulated sensor
when nothing runnable is found**. `mmco run sensors.yaml --seconds 10` records a configured session;
with no `--seconds` it runs until `mmco stop`, Ctrl-C, or SIGTERM. A running session hosts a loopback
control channel, so `mmco status` and `mmco stop` work from another shell (or `docker exec`). Every
session finalizes `manifest.json` + `session.log.jsonl` + `summary.md`. Kill or unplug a sensor
mid-session and the others keep recording while it auto-reconnects into a new segment — the summary
names the fault in plain English with its error code.

### Documents
- Design spec — [`docs/superpowers/specs/2026-05-20-mmco-sensor-backbone-design.md`](docs/superpowers/specs/2026-05-20-mmco-sensor-backbone-design.md)
- Implementation plan — [`docs/superpowers/plans/2026-05-20-mmco-sensor-backbone-plan.md`](docs/superpowers/plans/2026-05-20-mmco-sensor-backbone-plan.md)

### Phase progress

| Phase | Theme | Status |
|---|---|---|
| —  | Design spec (reviewed by two agents) | ✅ Done |
| —  | Phased implementation plan | ✅ Done |
| 0  | Project scaffolding & tooling | ✅ Done — package, tooling, paths; 4 tests green |
| 1  | Core types, contracts & error codes (pure) | ✅ Done — events, capabilities, driver ABC, clock, errors, manifest, log events |
| 2  | Event bus transport | ✅ Done — shared-memory ring, metadata queue, gen-checked producer/consumer |
| 3  | Simulated driver + driver host | ✅ Done — sim driver, control/log channels, cross-process host |
| 4  | Recorder + writers + manifest | ✅ Done — writer registry, parquet writer, manifest author, recorder + e2e |
| 5  | Supervisor: health & graceful degradation | ✅ Done — watchdog, gap logging, backoff restart, identity resume |
| 6  | Session log + auto-summary | ✅ Done — session.log.jsonl + readable summary.md, auto-generated |
| 7  | Control surface: config, CLI, live status | ✅ Done — YAML config + profiles, `mmco run`, live status table |
| 8  | Device discovery + default session + out-of-box | ✅ Done — injectable enumerators + stable identity, default-session builder, sim fallback, `mmco run` no-arg |
| 9  | USB webcam (V4L2) driver + video writer | ✅ Done — webcam driver (fake-capture seam), PyAV mp4 writer + timestamp sidecar, ±2 ms alignment |
| 10 | Containerization & one-command launch | ✅ Done — unbounded run + signals, loopback control daemon (`status`/`stop`), Dockerfile + compose, sim-fallback smoke |

Legend: ✅ done · 🔜 next up · ⬜ not started

All phases complete — the design spec is fully implemented.

### Known follow-ups

- **Linux multiprocessing validation (Phase 3).** Development is on Windows, where `spawn` is the
  default start method. The driver host spawns its child via `get_context("spawn")`, but the bus/log
  queues and the stop event are created from the default context. On Windows these coincide; on the
  Linux/WSL2 **runtime target** (default `fork`) this mixing must be verified — and if needed, all
  `multiprocessing` objects should be created from a single shared `spawn` context. Run the full suite
  (especially `tests/host/`) under WSL2/Linux and confirm green before relying on the cross-process
  path there. — tracked in [#14](https://github.com/shreyassanghvi/MMCO/issues/14)
- **Real device-enumerator validation (Phase 8).** Discovery's default enumerators glob `/dev`
  (`/dev/video*`, `/dev/ttyUSB*`/`/dev/ttyACM*`, `/dev/snd/pcmC*c`) and resolve stable identities via
  `/dev/by-id`; they return empty off Linux, so the suite covers the logic with injected fakes only.
  Confirm the real enumerators against actual hardware on Linux/WSL2 (USB attach needs `usbipd-win`).
  — tracked in [#15](https://github.com/shreyassanghvi/MMCO/issues/15)
- **Real webcam V4L2 backend (Phase 9).** The webcam driver's `v4l2` backend (PyAV opening
  `/dev/videoN`) only runs on Linux; every test uses the deterministic fake-capture backend, and the
  PyAV video writer encodes synthetic frames (works cross-platform, incl. Windows). Validate the real
  camera path via [`docs/hardware-checklist.md`](docs/hardware-checklist.md).
  — tracked in [#16](https://github.com/shreyassanghvi/MMCO/issues/16)
- **Docker image build/run (Phase 10).** ✅ Validated — the image builds and a sim-fallback session
  records to the host volume, with detached `docker exec mmco mmco status` / `mmco stop` exercised end
  to end. The full smoke test (`tests/integration/test_container_smoke.py`) runs wherever a Docker
  daemon is reachable and skips otherwise; the compose file is also validated via `docker compose config`.

---

## Tech stack

Python 3.14 · `multiprocessing` + `multiprocessing.shared_memory` · pytest · ruff · PyAV/ffmpeg
(video) · pyarrow/parquet (tabular) · PyYAML · V4L2 (webcam) · Docker/Compose. Runtime target is
Linux/WSL2; native (Rust/C++) hot paths added later only if profiling demands.

## Working conventions

- **No code without explicit approval** at any stage; ask when in doubt (see [`CLAUDE.md`](CLAUDE.md)).
- **TDD** — write the failing test first, then the minimal implementation.
- **Commits** — `<Feature name>: <what we did>` (e.g. `Paths: define recordings/<session_id> layout`).

## Repository layout

```
docs/superpowers/specs/   design spec
docs/superpowers/plans/   phased implementation plan
src/mmco/                 package (created in Phase 0)
tests/                    pytest suite (created in Phase 0)
recordings/               captured sessions — gitignored output, not source
Dockerfile                containerized service image
docker-compose.yml        one-command launch (volume + device-passthrough docs)
docker/entrypoint.sh      container entrypoint (records until stopped)
```

Each session writes `recordings/<session_id>/` containing `manifest.json` (the alignment contract),
per-stream files (`*.mp4` + per-frame timestamp sidecar, `*.parquet`), `session.log.jsonl`,
`summary.md`, and — while running — `control.addr` (the loopback control-channel port).
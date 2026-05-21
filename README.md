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

**Current stage:** design + plan approved; implementation not yet started.
**Active branch:** `impl/phase-0-scaffolding` (off `master`).
**Last updated:** 2026-05-21.

### Documents
- Design spec — [`docs/superpowers/specs/2026-05-20-mmco-sensor-backbone-design.md`](docs/superpowers/specs/2026-05-20-mmco-sensor-backbone-design.md)
- Implementation plan — [`docs/superpowers/plans/2026-05-20-mmco-sensor-backbone-plan.md`](docs/superpowers/plans/2026-05-20-mmco-sensor-backbone-plan.md)

### Phase progress

| Phase | Theme | Status |
|---|---|---|
| —  | Design spec (reviewed by two agents) | ✅ Done |
| —  | Phased implementation plan | ✅ Done |
| 0  | Project scaffolding & tooling | 🔜 Expanded into TDD steps; awaiting build |
| 1  | Core types, contracts & error codes (pure) | ⬜ Not started |
| 2  | Event bus transport | ⬜ Not started |
| 3  | Simulated driver + driver host | ⬜ Not started |
| 4  | Recorder + writers + manifest | ⬜ Not started |
| 5  | Supervisor: health & graceful degradation | ⬜ Not started |
| 6  | Session log + auto-summary | ⬜ Not started |
| 7  | Control surface: config, CLI, live status | ⬜ Not started |
| 8  | Device discovery + default session + out-of-box | ⬜ Not started |
| 9  | USB webcam (V4L2) driver + video writer | ⬜ Not started |
| 10 | Containerization & one-command launch | ⬜ Not started |

Legend: ✅ done · 🔜 next up · ⬜ not started

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
```
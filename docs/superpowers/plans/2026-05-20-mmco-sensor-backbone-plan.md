# MMCO Sensor-Backbone — Phased Implementation Plan (for review)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement, once phases are approved and expanded
> into bite-sized TDD steps. Steps will use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MMCO capture-box sensor-coordination backbone, delivered as a thin vertical slice
(simulated sensor + USB webcam) that runs out-of-the-box on Linux and demonstrates timestamped
multi-sensor recording with graceful degradation.

**Architecture:** Supervisor (core) process + one isolated process per sensor; events flow over a
per-driver shared-memory ring buffer; stamped at acquisition against one monotonic clock; recorded as
per-stream native files plus a session manifest, a structured session log, and a readable summary.

**Tech stack:** Python 3.14, `multiprocessing` + `multiprocessing.shared_memory`, pytest, PyAV/ffmpeg
(video), pyarrow/parquet (tabular), PyYAML, V4L2 (webcam), Docker/Compose.

**Conventions:** TDD (RED→GREEN→REFACTOR), commit messages `<Feature name>: <what we did>`, no code
without approval (see `CLAUDE.md`).

---

## What this demo showcases

Transfyr's mission — **help scientists spend less time documenting and debugging, and more time doing
the exploration they love.** Every phase serves that story:

- **Less documenting** — the scientist never hand-logs a session. MMCO auto-detects sensors, one command
  captures everything, and **the manifest + session log + readable summary are generated automatically**:
  time-aligned, ML-ready, and human-readable. (Phases 4, 6, 8)
- **Less debugging** — graceful degradation + auto-reconnect means a dropped cable or flaky camera never
  crashes the session. When something does go wrong, a **structured session log with generic error codes**
  says exactly what failed (e.g. device gone, driver crash, watchdog timeout) instead of leaving the
  scientist to guess. (Phases 5, 6)
- **More exploring** — zero-config, one command, always produces a recording. (Phases 8, 10)

The demo's punch-line moments are the **auto-generated, aligned recording + readable summary from a single
command** and the **unplug-the-camera-mid-session, it-just-keeps-going-and-tells-you-why** resilience.

---

## Phasing at a glance

| Phase | Theme | Demo-able outcome |
|---|---|---|
| 0  | Project scaffolding & tooling | `pytest` runs green on a clean repo |
| 1  | Core types, contracts & **error codes** (pure) | Unit-tested events, clock/offsets, manifest model, error-code taxonomy, log-event model |
| 2  | Event bus transport | Payloads + metadata move correctly under test |
| 3  | Simulated driver + driver host | A driver process emits stamped events the core drains |
| 4  | Recorder + writers + manifest | **First end-to-end recording** (sim → parquet + manifest); always-green CI path |
| 5  | Supervisor: health & graceful degradation | Kill sim mid-session → others keep recording, gap + error code logged, auto-reconnect |
| 6  | **Session log + auto-summary** | `session.log.jsonl` + readable `summary.md` written automatically |
| 7  | Control surface: config, CLI, live status | `mmco run <config>` + live status table + `mmco status` |
| 8  | Device discovery + default session + out-of-box | `mmco run` with no config → auto-detect or sim fallback → recording |
| 9  | USB webcam (V4L2) driver + video writer | **Full slice:** sim + webcam; unplug webcam → gap + reconnect |
| 10 | Containerization & one-command launch | `docker compose up` → recording; container story shipped |

Phases 0–9 deliver the spec's thin slice; Phase 10 ships the containerized-service wrapper. Out-of-scope
drivers (mic, serial IMU, IP camera, logfile), MCAP writer, ROS 2 packaging, and a native driver remain
**future work** and are not in this plan.

---

## Phase 0 — Project scaffolding & tooling

**Goal:** A clean, installable package with a passing test runner so every later phase has a home and a
green baseline.

**Branch:** `impl/phase-0-scaffolding` (off `master`).

**Build/tooling decisions (locked for this phase):**
- **Build backend:** `hatchling` with **src-layout** (`src/mmco/`) — modern, zero-boilerplate
  src-layout support, no `MANIFEST.in`.
- **Python:** `requires-python = ">=3.14"` (dev host confirmed on CPython 3.14.3).
- **Lint:** `ruff` (lint + format). Do **not** set `target-version` — ruff infers it from
  `requires-python`, avoiding an invalid `py314` literal on older ruff builds.
- **Types:** `mypy` is **optional** this phase — config only, not gating.
- **Commands:** run tools through the project venv interpreter as `python -m <tool>` so steps are
  shell-agnostic (PowerShell / WSL / PyCharm terminal).

> Outline task **0.3 (`.gitignore`)** is **already committed** — nothing to do there. The work below is
> 0.1 (package skeleton), 0.2 (tooling config), and 0.4 (recordings path convention). No source code is
> reproduced in this plan by repo convention; the steps state files, commands, and assertions only.

### Task 0.1 — Installable package skeleton

**Files:** create `pyproject.toml`, `src/mmco/__init__.py`, `tests/test_smoke.py`.

- [ ] **Step 1 — Write the failing smoke test.** In `tests/test_smoke.py`, add one test that imports
  `mmco` and asserts `mmco.__version__` is a non-empty `str`.
- [ ] **Step 2 — Run it; confirm it fails.** `python -m pytest tests/test_smoke.py -v` →
  FAIL with `ModuleNotFoundError: No module named 'mmco'` (package doesn't exist yet).
- [ ] **Step 3 — Create the package + build config.** Add `src/mmco/__init__.py` with a module
  docstring and `__version__ = "0.0.0"`. Add `pyproject.toml`: `[build-system]` using `hatchling`;
  `[project]` with `name = "mmco"`, `version = "0.0.0"`, `requires-python = ">=3.14"`, empty runtime
  `dependencies`, and a `dev` optional-dependencies group (`pytest`, `ruff`, `mypy`); a
  `[tool.hatch.build.targets.wheel]` entry pointing `packages` at `src/mmco`.
- [ ] **Step 4 — Install editable; confirm the test passes.** `python -m pip install -e ".[dev]"` then
  `python -m pytest tests/test_smoke.py -v` → install succeeds, **1 passed**.
- [ ] **Step 5 — Commit.** `git commit` the three files with message
  `Project Setup: add installable mmco package skeleton with smoke test`.

### Task 0.2 — Test & lint tooling configuration

**Files:** modify `pyproject.toml` (append tool config tables).

- [ ] **Step 1 — Add tool config.** Append `[tool.pytest.ini_options]` (`testpaths = ["tests"]`,
  `addopts = "-ra"`), `[tool.ruff]` (`line-length = 100`, `src = ["src", "tests"]`) with a
  `[tool.ruff.lint]` `select` of `["E", "F", "I", "UP", "B"]`, and an optional `[tool.mypy]`
  (`python_version = "3.14"`, `packages = ["mmco"]`, `strict = true`) — not gating yet.
- [ ] **Step 2 — Run the tooling; confirm clean.** `python -m ruff check .` → `All checks passed!`;
  `python -m pytest -v` discovers `tests/` and the smoke test PASSES.
- [ ] **Step 3 — Commit.** `git commit pyproject.toml` with message
  `Project Setup: configure pytest, ruff, and optional mypy`.

### Task 0.4 — Recordings output-path convention

**Files:** create `tests/test_paths.py`, `src/mmco/paths.py`.

Defines the on-disk layout every later phase writes into — `recordings/<session_id>/` containing
`manifest.json`, `session.log.jsonl`, `summary.md` (filenames match spec §5 and Phases 4/6). Pure path
math: **no I/O, no directory creation** in this module.

- [ ] **Step 1 — Write the failing tests.** In `tests/test_paths.py` assert: (a) `session_dir(base,
  session_id)` equals `base/recordings/<session_id>`; (b) `manifest_path`, `session_log_path`,
  `summary_path` of a session dir append the canonical filenames; (c) the four filename constants
  (`RECORDINGS_DIRNAME`, `MANIFEST_FILENAME`, `SESSION_LOG_FILENAME`, `SUMMARY_FILENAME`) are the
  expected stable strings.
- [ ] **Step 2 — Run; confirm it fails.** `python -m pytest tests/test_paths.py -v` →
  FAIL with `ModuleNotFoundError: No module named 'mmco.paths'`.
- [ ] **Step 3 — Write minimal implementation.** Create `src/mmco/paths.py` with the four filename
  constants and pure functions `recordings_root(base)`, `session_dir(base, session_id)`,
  `manifest_path(session_dir)`, `session_log_path(session_dir)`, `summary_path(session_dir)` — all
  `pathlib.Path` construction, no filesystem calls.
- [ ] **Step 4 — Run; confirm it passes.** `python -m pytest tests/test_paths.py -v` → **3 passed**.
- [ ] **Step 5 — Commit.** `git commit` both files with message
  `Paths: define recordings/<session_id> layout and artifact filenames`.

> **Deferred (YAGNI):** `session_id` *generation* (e.g. UTC-timestamp ids) and actual directory creation
> land where sessions start (Phase 4/7), not here.

**Phase 0 outcome:** `python -m pytest` runs green (smoke + paths), `python -m ruff check .` is clean,
`mmco` is importable, and the recordings layout is a single source of truth in `mmco.paths`.

---

## Phase 1 — Core types, contracts & error codes (pure, no I/O)

**Goal:** All the pure, in-process building blocks the rest of the system depends on — including the
error-code taxonomy and log-event model that make the system self-explaining — trivially TDD-able with
no processes or hardware.

**Tasks**
- **1.1 Event & metadata types** — `SensorEvent` (driver returns `payload` bytes/buffer +
  `payload_schema_ref`; host adds sensor_id, seq, t_acquire_ns) and the metadata record
  `{sensor_id, seq, t_acquire_ns, slot, length, gen}` that travels on the queue (`gen` = slot
  generation). Spec §4.0. *Tested by:* construction, equality, field validation; driver-set vs
  host-set fields enforced.
- **1.2 Stream capabilities & payload schema** — `StreamType` enum (video/audio/tabular),
  `Capabilities` (type, rate, schema descriptor). Schema descriptors per §4.0: tabular = ordered
  `{name, dtype}` columns; video = `{codec_or_raw, width, height, pixel_format}`; audio =
  `{sample_rate, channels, sample_format}`. *Tested by:* schema round-trips; invalid combos rejected.
- **1.3 `SensorDriver` abstract base (the plugin contract)** — `open() / read() / close() /
  capabilities / health()`; `health()` is a heartbeat, never a blocking call the core makes into a
  hung driver. Driver returns payload bytes only — **never touches shared memory** (the host copies).
  *Tested by:* a tiny in-test fake subclass satisfies the contract; abstract methods enforced.
- **1.4 Clock reference & latency-offset registry** — monotonic source wrapper; registry mapping
  sensor_id → offset; `t_event = t_acquire − offset`. *Tested by:* offset math, missing-offset default,
  monotonic↔wall anchor capture.
- **1.5 Session manifest model** — dataclasses for session + per-stream blocks. Each block has
  `{sensor_id, type, capabilities, latency_offset, dropped, segments[], gaps[]}` where a **segment** is
  `{file_path, start_timestamp, end_timestamp, block_index}` and a **gap** is
  `{start, end, reason, code}` (spec §5). `segments[]` (not a single `file_path`) so reconnects are
  representable. JSON (de)serialize. *Tested by:* round-trip serialization; multi-segment + gap
  ordering; schema fields present.
- **1.6 Error-code taxonomy** — an `ErrorCode` enum giving each failure a stable generic code + default
  human message, e.g. `MMCO-E001 device-not-found`, `E002 driver-crash`, `E003 watchdog-timeout`,
  `E004 device-disconnected`, `E005 shm-buffer-full`, `E006 config-invalid`, `E007 writer-failure`.
  *Tested by:* every code has a unique id + message; lookup by id; codes are stable strings.
- **1.7 Log-event model** — structured `LogEvent` (t_ns, level, optional `code: ErrorCode`, optional
  sensor_id, message, extra fields) with JSONL (de)serialize. The shared shape every component emits.
  *Tested by:* round-trip JSONL; code attaches to event; level filtering.

**Files:** `src/mmco/core/events.py`, `core/capabilities.py`, `core/driver.py`, `core/clock.py`,
`core/manifest.py`, `core/errors.py`, `core/logevent.py`; matching `tests/core/test_*.py`.

**Outcome:** A fully unit-tested pure core, including the error-code taxonomy and log-event shape used by
later phases. No processes yet.

---

## Phase 2 — Event bus transport (shared-memory ring + metadata queue)

**Goal:** Move payloads and metadata between a producer and the core without pickling big frames.

**Tasks**
- **2.1 Shared-memory ring buffer** — slot ring over `multiprocessing.shared_memory`, sized per stream
  `capabilities` (4K-video ring and IMU ring sized independently). Each slot carries a **generation
  counter `gen`**. **Non-blocking overflow = drop-oldest** + increment `dropped`, emitting
  `E005 shm-buffer-full`. **The core (not the driver) creates and `unlink()`s the segment**; drivers
  attach by name only; startup sweeps stale `mmco-*` segments and manages `resource_tracker`. *Tested
  by:* single-process write→read; wrap-around; drop-oldest on full + `dropped` increment; **read
  re-checks `gen` after copy and rejects an overwritten slot as a drop**; no leaked segment after a
  simulated producer crash.
- **2.2 Metadata queue** — records `{sensor_id, seq, t_acquire_ns, slot, length, gen}` over a
  `multiprocessing.Queue`. *Tested by:* ordering preserved; record encode/decode incl. `gen`.
- **2.3 Bus producer & consumer handles** — thin `BusProducer` (host side, copies payload into ring) /
  `BusConsumer` (core side, gen-checked read). *Tested by:* in-process producer→consumer delivers
  `(meta, payload)` intact; dropped-slot + gen-mismatch counters.

**Files:** `src/mmco/bus/ring.py`, `bus/metaqueue.py`, `bus/bus.py`; `tests/bus/test_*.py`.

**Outcome:** The bus moves data correctly under test, drops are counted (never silent), and shm has a
single owner with no leaks (still single-process; cross-process exercised in Phase 3).

---

## Phase 3 — Simulated driver + driver host (the process path)

**Goal:** Stand up the real cross-process acquisition path with a deterministic driver that doubles as
the primary test fixture.

**Tasks**
- **3.1 Simulated sensor driver** — deterministic tabular stream at a configured rate; **injectable
  failure modes** (crash, hang, slow) via config, used heavily in Phase 5. *Tested by:* emits expected
  values/rate; failure modes trigger on cue.
- **3.2 Driver host (process wrapper)** — generic runner that loads one driver, runs the acquisition
  loop, stamps `t_acquire` at the read, **copies the driver-returned payload into the ring** (driver
  never touches shm), pushes via `BusProducer`, and **emits `LogEvent`s** for open/close/error
  (carrying an `ErrorCode` on failure). *Tested by:* host run in a child process; core `BusConsumer`
  receives correctly stamped events; payload copied by host; lifecycle log events captured; clean
  shutdown on stop.
- **3.3 Control + log channel** — per-driver control channel (stop/flush) from core to host, and a log
  channel back so the core collects each host's `LogEvent`s. *Tested by:* stop signal terminates the loop
  promptly; no orphaned shared memory; log events delivered to the core.

**Files:** `src/mmco/drivers/simulated.py`, `src/mmco/host/driver_host.py`, `host/control.py`;
`tests/drivers/test_simulated.py`, `tests/host/test_driver_host.py`.

**Outcome:** A driver-host process emits stamped events (and log events) onto the bus and the core drains
them across a real process boundary.

---

## Phase 4 — Recorder + writers + manifest authoring

**Goal:** Turn drained events into files on disk plus a session manifest — the **first end-to-end
recording** and the always-green CI integration path.

**Tasks**
- **4.1 Writer interface** — `StreamWriter` (open/write_event/close) selected per stream type, and
  **registered through the same plugin mechanism as drivers** (a new stream type ships driver + writer
  together). Writers emit a per-block timestamp sidecar (parquet `t_event` column / mp4 PTS→monotonic
  table), not just first/last. *Tested by:* contract enforced; factory picks correct writer for a
  `StreamType`; sidecar emitted.
- **4.2 Parquet writer** — batches tabular rows (sim/serial) to parquet via pyarrow with a `t_event`
  column. *Tested by:* rows written, schema correct, per-row timestamps preserved, file readable back.
- **4.3 Manifest author** — opens manifest at session start (monotonic↔wall anchor), records per-stream
  `segments[]` + `latency_offset` + `dropped`, writes `manifest.json` on stop. *Tested by:* manifest
  matches written files; one segment per continuous run; timestamps monotonic.
- **4.4 Recorder wiring** — `BusConsumer` → route by sensor → writer + manifest segments; drops from the
  bus are recorded in the stream's `dropped` count. *Tested by:* end-to-end session with the simulated
  driver produces parquet + manifest; **integration test asserts files exist, timestamps monotonic,
  cross-stream alignment within ±2 ms, drops surfaced.**

**Files:** `src/mmco/record/writer.py`, `record/parquet_writer.py`, `record/manifest_author.py`,
`record/recorder.py`; `tests/record/test_*.py`, `tests/integration/test_session_simulated.py`.

**Outcome:** `clone → run-in-test → recording`. Simulated-only integration test is the CI backstop.

---

## Phase 5 — Supervisor: lifecycle, health, graceful degradation, auto-reconnect

**Goal:** Make the box resilient — a sensor can crash, hang, or vanish and the session survives.

**Tasks**
- **5.1 Supervisor spawn/monitor + shm ownership** — spawn driver hosts, track liveness, collect log
  events, **own the shm lifecycle** (create/`unlink`/recreate a driver's segment across restarts; sweep
  stale segments on startup), clean shutdown of all on stop. *Tested by:* N drivers start/stop cleanly;
  no leaked processes or shared memory after a crash; log events aggregated.
- **5.2 Watchdog & health policy** — detect crash (process exit → `E002`), hang (no events past a
  **per-stream watchdog timeout derived from the declared `rate`** → `E003`), and device-gone (`E004`).
  *Tested by:* sim failure modes (crash/hang/slow) each detected and mapped to the right code; a
  legitimately slow-but-alive stream is **not** falsely killed.
- **5.3 Gap logging** — on detection, **close the current segment**, append `{start, end, reason, code}`
  to the stream's manifest block, **emit a `LogEvent` with the code**, while **other streams keep
  recording**. *Tested by:* multi-driver session, one fails → gap + coded log recorded, others
  uninterrupted.
- **5.4 Restart with capped backoff + resume by stable identity** — re-spawn the dead driver with
  exponential backoff **up to a cap** (a device gone all session settles into the all-gap state, no
  spin-loop); on recovery the driver re-opens by **stable identity (by-id / VID:PID:serial), not the
  old `/dev` index**, and resumed data starts a **new segment** with the gap preserved; emit a reconnect
  `LogEvent`. *Tested by:* sim crash → re-spawn → resumes into a new segment; manifest shows gap then
  new segment; reconnect on a *different* device index still binds the right sensor.
- **5.5 Recorder write-failure policy** — a writer error / disk-full (`E007`) closes the affected
  stream's segment and opens a gap (like a stream fault) **without crashing the core**; other streams
  keep recording. *Tested by:* injected write failure → coded gap + session survives.

**Files:** `src/mmco/supervisor/supervisor.py`, `supervisor/watchdog.py`, `supervisor/policy.py`,
`supervisor/identity.py`; `tests/supervisor/test_*.py`, `tests/integration/test_degradation.py`.

**Outcome:** Kill/hang the simulated driver mid-session → other streams keep recording, gap + error code
are logged, the driver auto-reconnects (by stable identity) into a new segment. The resilience demo
(simulated). The core never crashes on a single stream's or the disk's failure.

---

## Phase 6 — Session log + auto-summary

**Goal:** Make the system self-documenting — every session leaves behind a machine-readable log of what
happened and a human-readable summary, with error codes that hint at any failures. This is the
"less documenting, less debugging" payoff.

**Tasks**
- **6.1 Session log writer** — append all collected `LogEvent`s to `session.log.jsonl` for the session
  (lifecycle, drops, gaps, reconnects, errors-with-codes), flushed on stop. *Tested by:* a session's log
  events land in JSONL in order; codes preserved; file re-readable.
- **6.2 Summary generator** — read `manifest.json` + `session.log.jsonl` and write a readable
  `summary.md`: streams captured, durations, sample counts, gaps/reconnects with their error codes and
  plain-English meaning, and cross-stream alignment quality. *Tested by:* summary lists every stream,
  reflects injected gaps with the correct code + message, and is generated without manual input.
- **6.3 Wire into session lifecycle** — recorder/supervisor finalize all three artifacts (manifest, log,
  summary) on stop. *Tested by:* integration test — a degraded simulated session yields manifest + log +
  summary, and the summary's reported failure matches the injected fault's error code.

**Files:** `src/mmco/record/session_log.py`, `record/summary.py`; `tests/record/test_session_log.py`,
`tests/record/test_summary.py`, `tests/integration/test_self_documenting_session.py`.

**Outcome:** Every session auto-produces `manifest.json` + `session.log.jsonl` + `summary.md`. Inject a
fault → the summary names what failed in plain English with its error code. No hand-documentation.

---

## Phase 7 — Control surface: config, CLI, live status

**Goal:** Let an operator drive and observe the box.

**Tasks**
- **7.1 Config model + YAML loader** — `sensors.yaml` → session config (sensors, drivers, recording
  profiles, output dir). *Tested by:* valid config parses; bad config gives a clear error with
  `E006 config-invalid`.
- **7.2 Recording profiles (per protocol + per-sensor override)** — `recording_profiles` give
  protocol-level defaults (e.g. `v4l2: {container, codec, crf}`, `alsa`, `serial`); a sensor's
  `profile_override` wins over its protocol default. Resolved at session start (spec §5.1). *Tested by:*
  protocol default applied; per-sensor override beats default; missing-key falls back; one non-default
  profile (`crf` override) resolves as expected.
- **7.3 CLI `run` / `stop`** — `mmco run <config>` boots supervisor+recorder; `mmco stop` ends the
  session and finalizes manifest + log + summary. *Tested by:* CLI invocation runs a short session and
  finalizes all artifacts (using sim driver).
- **7.4 Live status table** — render sensors, rate/fps, dropped frames, reconnect events, last error
  code; `mmco status`. *Tested by:* status snapshot reflects live counters (rendered from a fake
  supervisor state).

**Files:** `src/mmco/config/config.py`, `config/profiles.py`, `src/mmco/cli/main.py`,
`cli/status_view.py`; `tests/config/test_*.py`, `tests/cli/test_*.py`.

**Outcome:** `mmco run sensors.yaml` records with a live status table; `mmco status` shows live state.

---

## Phase 8 — Device discovery + default-session builder + out-of-box

**Goal:** `clone → one command → recording`, with no hand-editing.

**Tasks**
- **8.1 Device discovery** — enumerate `/dev/video*` (V4L2), ALSA/Pulse capture devices,
  `/dev/ttyUSB*`/`/dev/ttyACM*`; match each to a capable driver and record its **stable identity**
  (by-id path / USB VID:PID:serial) for reconnect. *Tested by:* discovery against a faked `/dev` +
  mocked enumerators returns expected device list with stable identities.
- **8.2 Default-session builder** — with no `sensors.yaml`, build a session from discovery; an explicit
  config always overrides. *Tested by:* discovery results → sensible default session.
- **8.3 Simulated fallback** — if nothing is found, default to the simulated sensor so a fresh clone
  always records. *Tested by:* empty discovery → session contains the sim driver and produces a
  recording.

**Files:** `src/mmco/discovery/discovery.py`, `discovery/default_session.py`; `tests/discovery/test_*.py`,
`tests/integration/test_out_of_box.py`.

**Outcome:** `mmco run` (no args) auto-detects sensors or falls back to simulated, then records.

---

## Phase 9 — USB webcam (V4L2) driver + video writer

**Goal:** Prove the heavy real-hardware path and complete the full slice.

**Tasks**
- **9.1 Webcam driver (V4L2)** — open by **stable identity** (resolve to the current `/dev/videoN`),
  read frames, return payload bytes for the host to copy; declare video capabilities; emit coded log
  events on open/disconnect. *Tested by:* unit tests against a **fake-V4L2 seam** (no hardware) covering
  open/read/close, disconnect (`E004`), and **reconnect on a different `/dev` index** resolving via
  stable identity.
- **9.2 Video writer (PyAV/ffmpeg)** — encode frames to mp4/mkv; record per-frame timestamps for the
  manifest. *Tested by:* synthetic frames → valid playable file; frame count + timing correct.
- **9.3 Latency offset for webcam** — declared/measured offset entry so video aligns with the tabular
  stream. *Tested by:* offset applied in manifest; alignment-within-tolerance integration assertion.
- **9.4 Manual hardware checklist** — documented steps to run the webcam on real Linux, incl. the
  `usbipd-win` attach note for WSL2. *(Docs, not a test.)*

**Files:** `src/mmco/drivers/webcam_v4l2.py`, `src/mmco/record/video_writer.py`,
`docs/hardware-checklist.md`; `tests/drivers/test_webcam_v4l2.py`, `tests/record/test_video_writer.py`.

**Outcome:** Full slice: simulated + webcam recording together; unplug/kill the webcam → gap + error code
logged → auto-reconnect; aligned mp4 + parquet + manifest + summary.

---

## Phase 10 — Containerization & one-command launch

**Goal:** Ship MMCO as a containerized service with a single launch command.

**Tasks**
- **10.1 Dockerfile** — Linux base with ffmpeg + Python deps; install `mmco`; non-root user. *Tested by:*
  image builds; `mmco --help` runs in-container.
- **10.2 docker-compose** — service def with a mounted host **volume** at `recordings/` (output survives
  the container) and **device passthrough** (`devices: ["/dev/video0:/dev/video0", ...]` + relevant
  `group_add`/udev for V4L2/ALSA/serial; documented privileged/`--device-cgroup-rule` fallback for
  dynamic device sets). `mmco status` attaches over the control socket when detached. *Tested by:*
  `docker compose up` runs a sim-only session and writes a recording to the host volume; `status`
  reachable on the detached container.
- **10.3 Entrypoint + default config** — container defaults to auto-discovery/sim fallback so
  `docker compose up` records with no extra steps even with **no devices mapped**. *Tested by:*
  container with no devices → sim fallback recording (manifest + log + summary) appears on the host.
- **10.4 README quickstart** — one-command instructions, hardware notes, output layout. *(Docs.)*

**Files:** `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`, `README.md`;
`tests/integration/test_container_smoke.py` (optional, env-gated).

**Outcome:** `docker compose up` → a recording on the host. The containerized-service story is shipped.

---

## Self-review (against the spec)

- **Spec §3 components** → plugin interface (1.3), driver host (3.2), event bus (2), supervisor (5),
  recorder (4), clock/offsets (1.4), device discovery (8.1), default-session builder (8.2), control
  surface (7). ✓
- **Spec §4 timestamping** → 1.4 (clock/offset), 3.2 (stamp at acquisition), 4.3 (manifest anchor). ✓
- **Spec §5 recording/manifest** → Phase 4 + 9.2 (video). ✓
- **Spec §6 degradation/auto-reconnect** → Phase 5. ✓
- **Spec §7 out-of-the-box** → Phase 8 + 10.3. ✓
- **Spec §8 thin slice (sim + webcam)** → Phases 3, 9; degradation demo in 5/9. ✓
- **Spec §9 testing (TDD, always-green CI, fault injection, hardware checklist)** → every phase is
  test-first; 4.4 CI path; 5 fault injection; 9.4 checklist. ✓
- **Spec §10–11 limitations/future work** → mic/serial/IP/logfile drivers, MCAP, ROS 2, native driver
  explicitly excluded. ✓
- **Value proposition (less documenting/debugging, more exploring)** → auto manifest+log+summary
  (4, 6), error-code taxonomy + coded session log (1.6, 1.7, 5, 6), zero-config one-command (8, 10). ✓

No spec requirement is left without a phase.

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

**Branch:** `impl/phase-1-core-types` (off `master`, after Phase 0 merge).

**Design decisions (locked for this phase):**
- **Pure stdlib only** — `dataclasses`, `enum`, `json`, `time`. **No new runtime dependencies**, no
  filesystem, no processes. Value types are **frozen dataclasses**; validation raises `ValueError`.
- **Package layout** — everything lands in a new `src/mmco/core/` subpackage; tests in `tests/core/`.
  Add `src/mmco/core/__init__.py` and `tests/core/__init__.py` in the first task and reuse them after.
- **Build order (dependency-safe), not numeric order:** 1.1 → 1.2 → 1.3 → 1.4 → **1.6 → 1.5 → 1.7**.
  The error-code taxonomy (1.6) ships before the manifest (1.5, `gap.code`) and the log-event (1.7,
  `event.code`) because both reference `ErrorCode`.
- **Commands:** `python -m pytest <path> -v` per task, `python -m ruff check .` before each commit
  (run via the project venv interpreter as in Phase 0). No source code is reproduced in this plan.

### Task 1.1 — Event & metadata value types

**Files:** create `src/mmco/core/__init__.py`, `src/mmco/core/events.py`, `tests/core/__init__.py`,
`tests/core/test_events.py`. (Spec §4.0.)

Three frozen value types: `DriverSample` (what a driver's `read()` returns: `payload: bytes`,
`payload_schema_ref: str`); `SensorEvent` (host-completed: the sample's fields **plus** `sensor_id`,
`seq`, `t_acquire_ns`, built via `SensorEvent.from_sample(sample, *, sensor_id, seq, t_acquire_ns)`);
and `EventMeta`, the queue record `{sensor_id, seq, t_acquire_ns, slot, length, gen}` (`gen` = slot
generation).

- [ ] **Step 1 — Write the failing tests.** In `tests/core/test_events.py` assert: (a) `DriverSample`
  holds `payload`/`payload_schema_ref` and compares by value; (b) `SensorEvent.from_sample(...)` copies
  the driver fields and sets the three host fields — confirming the driver→host split; (c) `EventMeta`
  constructs with all six fields and equality works; (d) negative `seq`, `slot`, `length`, `gen`, or
  `t_acquire_ns`, and empty `sensor_id`, raise `ValueError`.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/core/test_events.py -v` →
  FAIL (`ModuleNotFoundError: No module named 'mmco.core'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/core/__init__.py` (package docstring) and
  `src/mmco/core/events.py` with the three frozen dataclasses, the `from_sample` classmethod, and
  `__post_init__` validation raising `ValueError`. Add empty `tests/core/__init__.py`.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/core/test_events.py -v` → all pass.
- [ ] **Step 5 — Commit.** Message: `Events: add DriverSample, SensorEvent, and EventMeta value types`.

### Task 1.2 — Stream capabilities & payload schema

**Files:** create `src/mmco/core/capabilities.py`, `tests/core/test_capabilities.py`. (Spec §4.0.)

`StreamType` enum (`VIDEO`, `AUDIO`, `TABULAR`); three schema descriptors — `TabularSchema` (ordered
tuple of `Column{name, dtype}`), `VideoSchema{codec_or_raw, width, height, pixel_format}`,
`AudioSchema{sample_rate, channels, sample_format}`; and `Capabilities{type, rate, schema}` that
validates the schema descriptor matches the `type`.

- [ ] **Step 1 — Write the failing tests.** In `tests/core/test_capabilities.py` assert: (a) each
  schema descriptor round-trips through `to_dict`/`from_dict`; (b) `TabularSchema` preserves column
  order; (c) `Capabilities(StreamType.VIDEO, schema=VideoSchema(...))` is valid but pairing `VIDEO`
  with an `AudioSchema` raises `ValueError`; (d) an empty `TabularSchema` (no columns) raises
  `ValueError`.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/core/test_capabilities.py -v` → FAIL
  (`cannot import name 'capabilities'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/core/capabilities.py` with the enum, three frozen schema
  dataclasses (each with `to_dict`/`from_dict`), and `Capabilities` whose `__post_init__` enforces the
  type↔schema match. No I/O.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/core/test_capabilities.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Capabilities: add StreamType and per-type payload schemas`.

### Task 1.3 — `SensorDriver` abstract base (the plugin contract)

**Files:** create `src/mmco/core/driver.py`, `tests/core/test_driver.py`. (Spec §3.1.)

The plugin contract every driver implements: abstract `open()`, `read() -> DriverSample`, `close()`,
property `capabilities -> Capabilities`, and `health() -> DriverHealth`. `health()` is a
non-blocking heartbeat (a `DriverHealth` enum: `OK`, `DEGRADED`, `DOWN`) the driver reports — **never** a
blocking call the core makes into a hung driver. Drivers return payload bytes only and **never touch
shared memory** (the host copies); this is documented in the base class.

- [ ] **Step 1 — Write the failing tests.** In `tests/core/test_driver.py` assert: (a) instantiating
  `SensorDriver` directly raises `TypeError` (it is abstract); (b) a tiny in-test fake subclass that
  implements every abstract member instantiates, and its `read()` returns a `DriverSample` while
  `capabilities` returns a `Capabilities`; (c) a subclass that omits one abstract method cannot be
  instantiated (`TypeError`).
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/core/test_driver.py -v` → FAIL
  (`cannot import name 'driver'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/core/driver.py`: a `DriverHealth` enum and the
  `SensorDriver` ABC (`abc.ABC` + `@abstractmethod`), with docstrings stating the heartbeat and
  no-shared-memory rules.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/core/test_driver.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Driver Contract: add SensorDriver abstract base`.

### Task 1.4 — Clock reference & latency-offset registry

**Files:** create `src/mmco/core/clock.py`, `tests/core/test_clock.py`. (Spec §4.2.)

A `MonotonicClock` wrapper (`now_ns()` over `time.monotonic_ns()`; `capture_anchor()` returning a
`(monotonic_ns, wall_ns)` pair sampled once for the monotonic↔wall mapping) and an `OffsetRegistry`
mapping `sensor_id → offset_ns` with `event_time(sensor_id, t_acquire_ns) = t_acquire_ns − offset`
(`t_event = t_acquire − offset`, spec §4.2).

- [ ] **Step 1 — Write the failing tests.** In `tests/core/test_clock.py` assert: (a) an unknown
  sensor's offset defaults to `0`, so `event_time` returns `t_acquire_ns` unchanged; (b) after setting
  an offset, `event_time` subtracts it; (c) `capture_anchor()` returns two `int` ns values and
  `now_ns()` is non-decreasing across two successive calls.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/core/test_clock.py -v` → FAIL
  (`cannot import name 'clock'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/core/clock.py` with `MonotonicClock` and `OffsetRegistry`
  (plain stdlib `time`; default offset `0`; pure arithmetic).
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/core/test_clock.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Clock: add monotonic clock and latency-offset registry`.

### Task 1.6 — Error-code taxonomy *(built before 1.5 and 1.7)*

**Files:** create `src/mmco/core/errors.py`, `tests/core/test_errors.py`. (Spec §6.)

An `ErrorCode` enum giving each failure a stable generic code string and a default human message:
`MMCO-E001` device-not-found, `E002` driver-crash, `E003` watchdog-timeout, `E004`
device-disconnected, `E005` shm-buffer-full, `E006` config-invalid, `E007` writer-failure. Each member
exposes `.code` (e.g. `"MMCO-E001"`) and `.message`, plus a `from_code(code_str)` lookup.

- [ ] **Step 1 — Write the failing tests.** In `tests/core/test_errors.py` assert: (a) all members
  have unique `.code` values and non-empty `.message`; (b) `ErrorCode.from_code("MMCO-E003")` returns
  the watchdog-timeout member and an unknown string raises `ValueError`; (c) the seven `.code` strings
  equal their exact stable literals (`"MMCO-E001"` … `"MMCO-E007"`).
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/core/test_errors.py -v` → FAIL
  (`cannot import name 'errors'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/core/errors.py`: an `enum.Enum` whose members carry
  `(code, message)`, with a `code`/`message` property pair and a `from_code` classmethod.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/core/test_errors.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Error Codes: add MMCO error-code taxonomy`.

### Task 1.5 — Session manifest model *(depends on 1.2 + 1.6)*

**Files:** create `src/mmco/core/manifest.py`, `tests/core/test_manifest.py`. (Spec §5.)

Frozen dataclasses for the alignment contract: `Segment{file_path, start_timestamp, end_timestamp,
block_index}`; `Gap{start, end, reason, code: ErrorCode}`; `StreamBlock{sensor_id, type: StreamType,
capabilities: Capabilities, latency_offset, dropped: bool, segments: list[Segment], gaps:
list[Gap]}`; and `SessionManifest{session_id, monotonic_wall_anchor, output_dir, streams:
list[StreamBlock]}`. `segments[]` (not a single `file_path`) so a disconnect/reconnect is multiple
files with the hole preserved as a gap. JSON (de)serialize via `to_dict`/`from_dict` + `to_json`/
`from_json`.

- [ ] **Step 1 — Write the failing tests.** In `tests/core/test_manifest.py` assert: (a) a manifest
  with one stream, two `Segment`s and one `Gap` survives `to_json` → `from_json` equal to the original;
  (b) segment and gap **order is preserved**; (c) the serialized dict has the expected top-level keys
  and per-stream keys, and `gap.code` serializes to its stable `ErrorCode` code string and round-trips
  back to the `ErrorCode` member.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/core/test_manifest.py -v` → FAIL
  (`cannot import name 'manifest'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/core/manifest.py` with the four frozen dataclasses and
  symmetric `to_dict`/`from_dict` (+ `to_json`/`from_json` using stdlib `json`); serialize `StreamType`
  by name and `ErrorCode` by its `.code` string.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/core/test_manifest.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Manifest: add session manifest model with JSON round-trip`.

### Task 1.7 — Log-event model *(depends on 1.6)*

**Files:** create `src/mmco/core/logevent.py`, `tests/core/test_logevent.py`. (Spec §6.)

A `LogLevel` ordered enum (`DEBUG < INFO < WARNING < ERROR`) and a `LogEvent{t_ns, level: LogLevel,
message, code: ErrorCode | None = None, sensor_id: str | None = None, extra: dict}` — the shared shape
every component emits — with one-line JSONL `to_json`/`from_json`.

- [ ] **Step 1 — Write the failing tests.** In `tests/core/test_logevent.py` assert: (a) a `LogEvent`
  (including a non-empty `extra` dict) survives `to_json` → `from_json` equal to the original; (b) a
  `code` serializes to its stable `ErrorCode` string and round-trips, while an absent code serializes
  to JSON `null` and round-trips back to `None`; (c) `LogLevel` ordering lets you filter a list of
  events to those at/above a threshold (e.g. `>= WARNING`).
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/core/test_logevent.py -v` → FAIL
  (`cannot import name 'logevent'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/core/logevent.py`: an ordered `LogLevel` (e.g. `IntEnum`),
  the frozen `LogEvent` dataclass, and JSONL `to_json`/`from_json` handling the optional `code` and
  `sensor_id`.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/core/test_logevent.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Log Events: add structured LogEvent with JSONL round-trip`.

### Task 1.8 — Phase 1 gate

- [ ] **Step 1 — Full suite + lint.** `python -m pytest` → all phase 0 + phase 1 tests green;
  `python -m ruff check .` → `All checks passed!`.
- [ ] **Step 2 — Update README.** Flip the Phase 1 row to ✅ and the Phase 2 row to 🔜; refresh the
  test count and "Current stage" line.
- [ ] **Step 3 — Commit.** Message: `Docs: mark Phase 1 complete in progress README`.

**Files (Phase 1 total):** `src/mmco/core/{__init__,events,capabilities,driver,clock,errors,manifest,
logevent}.py`; matching `tests/core/test_*.py` (+ `tests/core/__init__.py`).

**Outcome:** A fully unit-tested pure core — value types, capability/schema descriptors, the driver
contract, clock/offset math, the error-code taxonomy, the session-manifest model, and the log-event
shape — all stdlib, no processes or hardware. Everything later phases build on is now type-checked and
round-trip tested.

---

## Phase 2 — Event bus transport (shared-memory ring + metadata queue)

**Goal:** Move payloads and metadata between a producer and the core without pickling big frames.

**Branch:** `impl/phase-2-event-bus` (off `master`, after Phase 1 merge).

**Design decisions (locked for this phase):**
- **Primitives:** `multiprocessing.shared_memory.SharedMemory` for the payload ring,
  `multiprocessing.Queue` for the metadata records. Stdlib `struct` lays out the ring header. **No new
  runtime dependencies.** All Phase 2 tests run **single-process** (create + attach in the same
  process); the real cross-process path is exercised in Phase 3.
- **Ring shape (round-robin overwrite store, keyed by `(slot, gen)`):** the segment holds a fixed
  header (`magic`, `n_slots`, `slot_size`, `write_idx`), then a per-slot table (`gen`, `length` per
  slot), then the `n_slots × slot_size` data region. The **metadata queue is the ordering authority**;
  the ring is random-access storage that the consumer reads by the `(slot, gen, length)` a meta record
  carries. `n_slots`/`slot_size` are sized per stream `capabilities` (a 4K-video ring and an IMU ring
  are sized independently). *(Why not a `read_idx`-based FIFO ring with producer-side drop-oldest: the
  ring and the separate meta queue can't stay in lockstep — when the ring drops its oldest slot the
  matching record is still in the queue, desyncing the consumer. Keying reads by `gen` avoids this and
  detects laps directly.)*
- **Ownership:** the **core creates and `unlink()`s** the segment (named with an `mmco-` prefix);
  drivers **attach by name only** and never `unlink`. A `sweep_stale_segments()` helper clears leftover
  `mmco-*` segments at startup.
- **Drops are never silent — in two honest places:** (1) the **consumer** detects a *lapped slot* —
  `read_slot` compares the meta's `gen` to the slot's current `gen` (and re-reads `gen` after copying);
  a mismatch means the slot was overwritten before/during the read, so it returns `None` and the
  consumer counts a drop rather than returning torn bytes. (2) the **producer** detects *backpressure* —
  when the bounded meta queue is full, `publish` counts a drop and surfaces
  `ErrorCode.SHM_BUFFER_FULL` to the caller (the host turns that into a `LogEvent` in Phase 3). The
  ring's `write()` itself always succeeds (it overwrites the oldest slot); fullness is observed at the
  queue, not the ring.
- **Platform note:** POSIX `resource_tracker`/`unlink` semantics differ on Windows; the stale-sweep /
  leak test is Linux-only (`@pytest.mark.skipif(sys.platform == "win32")`). Read/write/wrap/drop/gen
  tests are platform-neutral. Commands run via the project venv interpreter (`python -m ...`) as before.

### Task 2.1 — Shared-memory ring buffer

**Files:** create `src/mmco/bus/__init__.py`, `src/mmco/bus/ring.py`, `tests/bus/__init__.py`,
`tests/bus/test_ring.py`. (Spec §3.1, §4.1.)

A `RingBuffer` with `create(n_slots, slot_size)` (owns the segment, zero-inits the header) and
`attach(name, n_slots, slot_size)` (attaches, never owns); `close()` detaches and `unlink()` (owner
only) frees. `write(payload) -> SlotRef(slot, gen, length)` round-robins the write index, bumps the
slot's `gen`, and writes length+bytes; it **always succeeds** (overwrites the oldest slot).
`read_slot(slot, gen, length) -> bytes | None` does a random-access copy keyed by a meta record and
re-checks `gen` before and after the copy (returns `None` on mismatch — the slot was lapped).

- [ ] **Step 1 — Write the failing tests.** In `tests/bus/test_ring.py` assert: (a) a single-process
  `create` → `write(b"...")` → `read_slot(*ref)` returns the same bytes; (b) writing more than
  `n_slots` payloads wraps around and each just-written slot is readable via its returned `SlotRef`;
  (c) a slot's `gen` increases each time it is reused (write `n_slots + 1` payloads, assert the reused
  slot's second `SlotRef.gen` is greater than its first); (d) after a slot is overwritten, a
  `read_slot` with the **stale** `gen` returns `None` (lapped slot rejected, not torn bytes);
  (e) `write` of a payload larger than `slot_size` raises `ValueError`.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/bus/test_ring.py -v` → FAIL
  (`No module named 'mmco.bus'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/bus/__init__.py`, `src/mmco/bus/ring.py` with a `SlotRef`
  frozen dataclass and the `RingBuffer` class (stdlib `struct` for the header; `create`/`attach`/
  `close`/`unlink`; `write`/`read_slot`). Add empty `tests/bus/__init__.py`.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/bus/test_ring.py -v` → all pass; ensure
  each test `close()`s/`unlink()`s its segment so the suite leaves no segments behind.
- [ ] **Step 5 — Add the stale-sweep test + helper (Linux-only).** Add a
  `@pytest.mark.skipif(sys.platform == "win32")` test that creates a leftover `mmco-*` segment, calls
  `sweep_stale_segments()`, and asserts it is gone; implement `sweep_stale_segments()` in `ring.py`.
  Run `python -m pytest tests/bus/test_ring.py -v` (the new test **skips** on the Windows dev host).
- [ ] **Step 6 — Commit.** Message: `Ring Buffer: add shared-memory SPSC ring with gen-checked reads`.

### Task 2.2 — Metadata queue

**Files:** create `src/mmco/bus/metaqueue.py`, `tests/bus/test_metaqueue.py`. (Spec §4.0.)

A thin `MetaQueue` over `multiprocessing.Queue` carrying `EventMeta` records
(`{sensor_id, seq, t_acquire_ns, slot, length, gen}`). `put(meta) -> bool` is non-blocking (returns
`False` if full); `get(timeout) -> EventMeta | None`.

- [ ] **Step 1 — Write the failing tests.** In `tests/bus/test_metaqueue.py` assert: (a) `put` then
  `get` returns an `EventMeta` **equal** to the original, including `gen` (encode/decode survives the
  queue's pickling); (b) FIFO order is preserved across several `put`s; (c) `get` on an empty queue
  with a short timeout returns `None`; (d) on a `MetaQueue(maxsize=1)`, a second `put` returns `False`
  (non-blocking, queue full) rather than blocking.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/bus/test_metaqueue.py -v` → FAIL
  (`cannot import name 'metaqueue'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/bus/metaqueue.py` wrapping `multiprocessing.Queue`
  (optional `maxsize`), with non-blocking `put` (catch `queue.Full` → `False`) and `get` with timeout
  (catch `queue.Empty` → `None`).
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/bus/test_metaqueue.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Meta Queue: add ordered metadata queue over multiprocessing.Queue`.

### Task 2.3 — Bus producer & consumer handles

**Files:** create `src/mmco/bus/bus.py`, `tests/bus/test_bus.py`. (Spec §4.1.)

`BusProducer(ring, metaqueue)` with `publish(sensor_id, seq, t_acquire_ns, payload) -> ErrorCode |
None`: copies the payload into the ring, builds the `EventMeta` from the returned `SlotRef`, and puts
it on the queue. If the queue is full it counts a drop and returns `ErrorCode.SHM_BUFFER_FULL`
(backpressure); otherwise returns `None`. Exposes a `dropped` counter.
`BusConsumer(ring, metaqueue)` with `poll(timeout) -> tuple[EventMeta, bytes] | None`: gets a meta,
reads the ring with gen-recheck, counts a drop and returns `None` on gen-mismatch (lapped slot), else
returns the `(meta, payload)` pair. Exposes its own `dropped` counter.

- [ ] **Step 1 — Write the failing tests.** In `tests/bus/test_bus.py` assert: (a) an in-process
  `publish(...)` followed by `poll(...)` returns `(EventMeta, payload)` with the payload bytes and all
  meta fields intact, and `publish` returned `None`; (b) on a producer whose queue is full
  (`MetaQueue(maxsize=1)` already holding one record), the next `publish` returns
  `ErrorCode.SHM_BUFFER_FULL` and the producer's `dropped` count rises; (c) a `poll` whose meta points
  at a slot whose `gen` has since advanced (ring overrun past `n_slots`) returns `None` and increments
  the consumer's `dropped` counter — no torn payload is ever returned.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/bus/test_bus.py -v` → FAIL
  (`cannot import name 'bus'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/bus/bus.py` with `BusProducer` and `BusConsumer` composing
  the `RingBuffer` + `MetaQueue`, building `EventMeta` from `SlotRef`, and exposing `dropped` counters.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/bus/test_bus.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Event Bus: add producer/consumer handles over ring + meta queue`.

### Task 2.4 — Phase 2 gate

- [ ] **Step 1 — Full suite + lint.** `python -m pytest` → all phases green (the Linux-only sweep test
  shows as skipped on Windows); `python -m ruff check .` → `All checks passed!`.
- [ ] **Step 2 — Update README.** Flip the Phase 2 row to ✅ and the Phase 3 row to 🔜; refresh the
  test count and "Current stage" line.
- [ ] **Step 3 — Commit.** Message: `Docs: mark Phase 2 complete in progress README`.

**Files (Phase 2 total):** `src/mmco/bus/{__init__,ring,metaqueue,bus}.py`; matching
`tests/bus/test_*.py` (+ `tests/bus/__init__.py`).

**Outcome:** The bus moves data correctly under test, drops are counted (never silent) in both honest
places — the producer's queue-full backpressure (`SHM_BUFFER_FULL`) and the consumer's gen-mismatch
detection — and shm has a single owner with no leaks (still single-process; cross-process exercised in
Phase 3).

---

## Phase 3 — Simulated driver + driver host (the process path)

**Goal:** Stand up the real cross-process acquisition path with a deterministic driver that doubles as
the primary test fixture.

**Branch:** `impl/phase-3-sim-driver` (off `master`, after Phase 2 merge).

**Design decisions (locked for this phase):**
- **Start method `spawn`.** Set `multiprocessing.set_start_method("spawn")` (Windows' default; pin it
  so Linux behaves identically). Consequence: every `Process` target is a **module-level function** in
  `src/` (never a closure or test-local function — spawn re-imports the module), and all args must be
  ForkingPickler-safe.
- **Ownership / wiring.** The **core** creates the `RingBuffer` (owner), the meta `MetaQueue`, a log
  channel, and a stop signal, then spawns the host as a child `Process` running
  `run_driver_host(...)`, passing the ring **name + dims** and the queues/stop as `Process` args. The
  host **attaches** the ring by name (never creates/unlinks), builds a `BusProducer`, and on exit
  detaches; the core `unlink()`s the segment.
- **Driver never touches shm.** The host stamps `t_acquire = clock.now_ns()` at the read, **copies**
  the driver-returned `DriverSample.payload` into the ring via `BusProducer`, and paces to the
  driver's nominal rate. Each process uses its own `MonotonicClock` (cross-process clock offset is out
  of scope per spec §10; alignment is validated within tolerance in the Phase 9 slice).
- **Everything is observable.** The host emits `LogEvent`s for `open` / `close` / `error` on the log
  channel; a driver `read()` that raises becomes a `LogEvent(code=ErrorCode.DRIVER_CRASH)` and the host
  exits cleanly.
- **Build order:** 3.1 → **3.3 → 3.2** → 3.4 (the control + log channel primitives are built before the
  host loop that consumes them).
- **Test hygiene.** Tests spawn **real child processes**, bounded by consuming a fixed number of events
  then requesting stop with a `join(timeout)`; timing assertions use generous timeouts to avoid
  flakiness; the no-orphaned-segment check is Linux-only (`skipif(win32)`). Commands run via the
  project venv interpreter.

### Task 3.1 — Simulated sensor driver

**Files:** create `src/mmco/drivers/__init__.py`, `src/mmco/drivers/simulated.py`,
`tests/drivers/__init__.py`, `tests/drivers/test_simulated.py`. (Spec §3.1, §9.)

A `SimulatedDriver(SensorDriver)` producing a **deterministic** tabular stream: each `read()` returns a
`DriverSample` whose payload is the current sample index packed with `struct` (schema ref `"sim.v1"`),
and `capabilities` is a `TABULAR` `Capabilities` at the configured rate with a one-column
`TabularSchema`. A `SimConfig` (frozen) carries `sensor_id`, `rate_hz`, and an optional **failure
mode** — `crash` (raise after N reads), `slow` (sleep `delay_s` per read), or `hang` (block in `read()`
until `close()` releases it, so tests never dangle) plus `failure_after`.

- [ ] **Step 1 — Write the failing tests.** In `tests/drivers/test_simulated.py` assert: (a)
  `capabilities` is `TABULAR` at `rate_hz` with the expected single-column schema; (b) successive
  `read()`s return payloads that decode to a strictly increasing counter `0, 1, 2, …`; (c) with
  `failure="crash", failure_after=3`, the first three reads succeed and the fourth raises; (d) with
  `failure="slow", delay_s=…`, a `read()` takes at least `delay_s` (measured); (e) with
  `failure="hang"`, a `read()` called on a worker thread is still alive after a short wait and returns
  only after `close()` releases it (thread joins).
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/drivers/test_simulated.py -v` → FAIL
  (`No module named 'mmco.drivers'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/drivers/__init__.py`, `src/mmco/drivers/simulated.py` with
  `SimConfig`, the `SimulatedDriver` (counter payload via `struct`; `health()` returns
  `DriverHealth.OK`; `hang` waits on a `threading.Event` that `close()` sets). Add empty
  `tests/drivers/__init__.py`.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/drivers/test_simulated.py -v` → pass.
- [ ] **Step 5 — Commit.** Message:
  `Simulated Driver: add deterministic tabular sim with injectable failure modes`.

### Task 3.3 — Control + log channels *(built before the host)*

**Files:** create `src/mmco/host/__init__.py`, `src/mmco/host/control.py`,
`tests/host/__init__.py`, `tests/host/test_control.py`. (Spec §3.1.)

Two thin, picklable channels the core hands a host. `Control` wraps a `multiprocessing.Event` with
`request_stop()` and `stop_requested() -> bool`. `LogChannel` wraps a `multiprocessing.Queue` of
`LogEvent`s with non-blocking `emit(event) -> bool` (host side) and `drain(timeout) -> list[LogEvent]`
(core side).

- [ ] **Step 1 — Write the failing tests.** In `tests/host/test_control.py` assert: (a) a fresh
  `Control` reports `stop_requested()` is `False`, and `True` after `request_stop()`; (b) `LogChannel`
  round-trips a `LogEvent` (including its `code`) through `emit` then `drain`; (c) `drain` on an empty
  channel returns `[]` within the timeout; (d) `drain` returns multiple emitted events in FIFO order.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/host/test_control.py -v` → FAIL
  (`No module named 'mmco.host'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/host/__init__.py`, `src/mmco/host/control.py` with
  `Control` (over `mp.Event`) and `LogChannel` (over `mp.Queue`, non-blocking `emit`, `drain` that
  collects until empty or timeout). Add empty `tests/host/__init__.py`.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/host/test_control.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Control Channel: add stop signal and log channel for driver hosts`.

### Task 3.2 — Driver host (cross-process acquisition runner)

**Files:** create `src/mmco/host/driver_host.py`, `tests/host/test_driver_host.py`. (Spec §3.1, §4.1.)

A module-level `run_driver_host(config, ring_name, n_slots, slot_size, metaqueue, control, log_channel)`
(the spawn target) that attaches the ring, builds a `BusProducer`, emits an `open` `LogEvent`, then
loops: `read()` the driver → stamp `t_acquire` → `publish` → pace to `rate_hz`, checking
`control.stop_requested()` each iteration; on a driver exception it emits
`LogEvent(code=ErrorCode.DRIVER_CRASH)` and exits; on stop it `close()`s the driver, emits a `close`
`LogEvent`, and detaches the ring. A small `spawn_driver_host(...)` core-side helper wires the ring +
queues and returns the started `Process`.

- [ ] **Step 1 — Write the failing tests.** In `tests/host/test_driver_host.py` (using a
  `SimulatedDriver` config) assert: (a) with the host running in a real child process, a core
  `BusConsumer` polls **correctly stamped** events — `t_acquire_ns` is positive and non-decreasing and
  payloads decode to the expected `0, 1, 2, …` counter; (b) the `LogChannel` yields an `open` event at
  startup and a `close` event after stop; (c) requesting stop makes the child exit and
  `process.join(timeout)` succeeds (the process is no longer alive); (d) with a `crash`-mode sim, the
  core receives the pre-crash events followed by a `LogEvent` carrying `ErrorCode.DRIVER_CRASH`, and
  the child exits.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/host/test_driver_host.py -v` → FAIL
  (`cannot import name 'driver_host'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/host/driver_host.py` with `run_driver_host` and
  `spawn_driver_host`; pin the start method to `spawn`; ensure clean teardown (driver `close()`, ring
  detach) on both stop and crash paths.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/host/test_driver_host.py -v` → pass
  (allow generous join timeouts). Confirm no segment is leaked after the test (the core `unlink()`s).
- [ ] **Step 5 — Commit.** Message:
  `Driver Host: add cross-process acquisition runner emitting stamped events`.

### Task 3.4 — Phase 3 gate

- [ ] **Step 1 — Full suite + lint.** `python -m pytest` → all phases green (Linux-only checks skip on
  Windows); `python -m ruff check .` (verify exit code `0`) → `All checks passed!`.
- [ ] **Step 2 — Update README.** Flip the Phase 3 row to ✅ and the Phase 4 row to 🔜; refresh the
  test count and "Current stage" line.
- [ ] **Step 3 — Commit.** Message: `Docs: mark Phase 3 complete in progress README`.

**Files (Phase 3 total):** `src/mmco/drivers/{__init__,simulated}.py`,
`src/mmco/host/{__init__,control,driver_host}.py`; matching `tests/drivers/` + `tests/host/` modules.

**Outcome:** A driver-host process emits stamped events (and log events) onto the bus and the core
drains them across a real process boundary, with clean shutdown on stop and an error-coded log event on
driver crash.

---

## Phase 4 — Recorder + writers + manifest authoring

**Goal:** Turn drained events into files on disk plus a session manifest — the **first end-to-end
recording** and the always-green CI integration path.

**Branch:** `impl/phase-4-recorder` (off `master`, after Phase 3 merge).

**Design decisions (locked for this phase):**
- **New runtime dependency: `pyarrow`** (parquet). Added to `[project.dependencies]` in
  `pyproject.toml` and installed into the venv during Task 4.2. First non-stdlib runtime dep.
- **Tabular payload convention.** A tabular `DriverSample.payload` is the row's values packed with
  `struct` in `TabularSchema` column order. The writer derives both a `struct` format and an Arrow
  schema from a small dtype map (`int64`/`int32`/`float32`/`float64` → struct codes / `pyarrow` types).
  Writers always emit a per-row `t_event` column (for parquet the timestamp sidecar lives in-file).
- **`t_event` is computed by the recorder** via the Phase 1 `OffsetRegistry`
  (`t_event = t_acquire − offset`); the manifest stores each stream's `latency_offset`.
- **Writer registry now, full plugin unification later.** A simple `StreamType → writer class`
  registry selects the writer this phase; merging it into the *driver* entry-point plugin mechanism
  (so a stream type ships driver + writer together) is Phase 8 — noted, not built here.
- **One continuous run → one segment → one file.** Multi-segment streams (reconnects) are exercised in
  Phase 5; here each stream yields a single segment.
- **Scope of the integration test.** Asserts files exist, the manifest matches the written files,
  per-row timestamps are monotonic, and bus drops are surfaced in the stream's `dropped`. The strict
  **±2 ms cross-stream alignment** check (spec §4.2) needs a real reference stream and is **deferred to
  Phase 9** (sim + webcam) — flagged so it isn't lost.
- Tests write to pytest's `tmp_path`; commands run via the project venv interpreter.
- **Build order:** 4.1 → 4.2 → 4.3 → 4.4 → 4.5 gate.

### Task 4.1 — Writer contract & per-type registry

**Files:** create `src/mmco/record/__init__.py`, `src/mmco/record/writer.py`,
`tests/record/test_writer.py`. (Spec §5.)

A `StreamWriter` ABC: `open()`, `write_event(t_event_ns, payload)`, `close()`, plus read-only
`file_path`, `start_timestamp`, `end_timestamp` (first/last `t_event` seen). A module-level registry —
`register_writer(stream_type, cls)` and `writer_for(stream_type, *, capabilities, file_path)` — selects
the writer class for a `StreamType`.

- [ ] **Step 1 — Write the failing tests.** In `tests/record/test_writer.py` assert: (a) `StreamWriter`
  cannot be instantiated directly (`TypeError`); (b) a tiny in-test fake writer subclass registered via
  `register_writer` is returned by `writer_for` for its `StreamType`; (c) `writer_for` on an
  unregistered `StreamType` raises (`KeyError`/`ValueError`); (d) the fake records `start_timestamp`/
  `end_timestamp` as the first/last `t_event` passed to `write_event`.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/record/test_writer.py -v` → FAIL
  (`No module named 'mmco.record'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/record/__init__.py`, `src/mmco/record/writer.py` with the
  `StreamWriter` ABC and the registry functions (a private dict; `writer_for` raises on miss).
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/record/test_writer.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Writers: add StreamWriter contract and per-type writer registry`.

### Task 4.2 — Parquet writer

**Files:** modify `pyproject.toml` (add `pyarrow`); create `src/mmco/record/parquet_writer.py`,
`tests/record/test_parquet_writer.py`. (Spec §5, §5.1.)

A `ParquetWriter(StreamWriter)` for `TABULAR` streams: derives a `struct` format + Arrow schema from
the `Capabilities` `TabularSchema`, buffers decoded rows on `write_event`, and on `close` writes a
parquet file whose columns are `t_event` (int64) plus the schema columns. Registers itself for
`StreamType.TABULAR`.

- [ ] **Step 1 — Add the dependency.** Add `pyarrow` to `[project.dependencies]` in `pyproject.toml`;
  run `python -m pip install -e ".[dev]"` so the venv has it.
- [ ] **Step 2 — Write the failing tests.** In `tests/record/test_parquet_writer.py` (writing under
  `tmp_path`, sim-style `struct.pack("<q", n)` payloads, a one-column `int64` schema) assert: (a) after
  `open` → three `write_event(t, payload)` → `close`, the parquet file exists and reads back (via
  `pyarrow.parquet`) with three rows; (b) the `t_event` column equals the timestamps passed, in order;
  (c) the data column decodes to the original values; (d) `start_timestamp`/`end_timestamp` equal the
  first/last `t_event`.
- [ ] **Step 3 — Run; confirm RED.** `python -m pytest tests/record/test_parquet_writer.py -v` → FAIL
  (`cannot import name 'parquet_writer'`).
- [ ] **Step 4 — Implement.** Add `src/mmco/record/parquet_writer.py` with the dtype map, row buffering,
  and the pyarrow write on `close`; call `register_writer(StreamType.TABULAR, ParquetWriter)`.
- [ ] **Step 5 — Run; confirm GREEN.** `python -m pytest tests/record/test_parquet_writer.py -v` → pass.
- [ ] **Step 6 — Commit.** Message: `Parquet Writer: add pyarrow tabular writer with per-row t_event`.

### Task 4.3 — Manifest author

**Files:** create `src/mmco/record/manifest_author.py`, `tests/record/test_manifest_author.py`.
(Spec §5.)

A `ManifestAuthor` that opens at session start with the `session_id`, `output_dir`, and a
`ClockAnchor`; `add_stream(sensor_id, type, capabilities, latency_offset)`; `add_segment(sensor_id,
segment)`; `set_dropped(sensor_id, n)`; and `write(path)` that assembles a Phase 1 `SessionManifest`
and writes `manifest.json`.

- [ ] **Step 1 — Write the failing tests.** In `tests/record/test_manifest_author.py` (under
  `tmp_path`) assert: (a) authoring one stream with one `Segment` + a `dropped` count, then `write`,
  produces a `manifest.json` that `SessionManifest.from_json` reads back equal to what was authored;
  (b) the stream block carries the `latency_offset` and `dropped` given; (c) the segment's
  `start_timestamp <= end_timestamp` (monotonic).
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/record/test_manifest_author.py -v` → FAIL
  (`cannot import name 'manifest_author'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/record/manifest_author.py` building `StreamBlock`s +
  `SessionManifest` from the accumulated state and writing it via `to_json`.
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/record/test_manifest_author.py -v` → pass.
- [ ] **Step 5 — Commit.** Message: `Manifest Author: assemble and write session manifest.json`.

### Task 4.4 — Recorder wiring (first end-to-end recording)

**Files:** create `src/mmco/record/recorder.py`, `tests/record/test_recorder.py`,
`tests/integration/test_session_simulated.py`. (Spec §4.1, §5.)

A `Recorder` that, given a `BusConsumer`, a per-sensor `Capabilities` map, an `OffsetRegistry`, a
`session_id`, and a base output dir, drains the bus: routes each `(meta, payload)` by `sensor_id` to
that sensor's writer (created lazily under `recordings/<session_id>/`), writing `t_event =
offsets.event_time(sensor_id, meta.t_acquire_ns)`; on stop it closes writers, records each stream's
`dropped` (from the consumer), and asks the `ManifestAuthor` to write `manifest.json`.

- [ ] **Step 1 — Write the failing unit test.** In `tests/record/test_recorder.py`, drive a `Recorder`
  directly by publishing a handful of tabular events through an in-process bus, run one drain pass,
  stop, and assert: a parquet file and `manifest.json` exist under `recordings/<session_id>/`, and the
  manifest's single segment `file_path` matches the written parquet.
- [ ] **Step 2 — Run; confirm RED.** `python -m pytest tests/record/test_recorder.py -v` → FAIL
  (`cannot import name 'recorder'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/record/recorder.py` (lazy per-sensor writer creation via
  `writer_for`, `t_event` via the offset registry, dropped from `consumer.dropped`, manifest on stop).
- [ ] **Step 4 — Run; confirm GREEN.** `python -m pytest tests/record/test_recorder.py -v` → pass.
- [ ] **Step 5 — Write the end-to-end integration test.** In
  `tests/integration/test_session_simulated.py`, spawn a `SimulatedDriver` host (Phase 3), run the
  `Recorder` against the bus for a fixed number of events, stop, and assert: `manifest.json` + the
  parquet exist; the parquet's `t_event` column is **monotonic non-decreasing**; the manifest segment's
  `start/end` bracket the data; and any bus drops appear in the stream's `dropped`. *(The ±2 ms
  cross-stream alignment assertion is deferred to Phase 9.)*
- [ ] **Step 6 — Run; confirm GREEN.** `python -m pytest tests/integration/test_session_simulated.py -v`
  → pass (generous timeouts).
- [ ] **Step 7 — Commit.** Message:
  `Recorder: wire bus consumer to writers and manifest (first end-to-end recording)`.

### Task 4.5 — Phase 4 gate

- [ ] **Step 1 — Full suite + lint.** `python -m pytest` → all phases green (Linux-only checks skip on
  Windows); `python -m ruff check .` (verify exit `0`).
- [ ] **Step 2 — Update README.** Flip Phase 4 to ✅, Phase 5 to 🔜; refresh test count + stage line;
  note the first end-to-end recording works.
- [ ] **Step 3 — Commit.** Message: `Docs: mark Phase 4 complete in progress README`.

**Files (Phase 4 total):** `src/mmco/record/{__init__,writer,parquet_writer,manifest_author,
recorder}.py`; `tests/record/test_*.py`; `tests/integration/test_session_simulated.py`.

**Outcome:** `clone → run-in-test → recording`. A simulated-only end-to-end session writes parquet +
`manifest.json` with monotonic per-row timestamps and surfaced drops — the always-green CI backstop.

---

## Phase 5 — Supervisor: lifecycle, health, graceful degradation, auto-reconnect

**Goal:** Make the box resilient — a sensor can crash, hang, or vanish and the session survives.

**Branch:** `impl/phase-5-supervisor` (off `master`, after Phase 4 merge).

**Design decisions (locked for this phase):**
- **Per-sensor runtime.** Each sensor gets its own ring (sized from its capabilities), `MetaQueue`,
  `Control`, `LogChannel`, host process, and `BusConsumer`. The **supervisor owns them all** and is the
  single shm owner — it creates/`unlink`s/recreates a sensor's segment across restarts and sweeps stale
  `mmco-*` segments at startup.
- **Deterministic watchdog.** Health checks take an explicit monotonic `now` (and the host's liveness),
  so tests inject time instead of sleeping. Hang timeout = `max(factor / rate_hz, floor_s)`.
- **Error-code sources:** process exited unexpectedly → `E002`; no events past the watchdog timeout
  while still alive → `E003`; the driver signalling device-gone (`DeviceDisconnectedError`) → `E004`
  (a generic read error stays `E002`); a writer/disk failure → `E007`.
- **Capped backoff, never give up.** `backoff(attempt) = min(base · 2^attempt, cap)`; a device gone all
  session keeps retrying at the cap (the stream settles into an all-gap state — no spin-loop).
- **Resume by stable identity into a new segment.** Re-spawn re-binds by the spec's stable `identity`
  (by-id / VID:PID:serial), **not** a transient device index; resumed data opens a **new segment** with
  the gap preserved between.
- **Core never crashes on one stream's fault.** Stream and disk faults become coded gaps; the other
  streams keep recording.
- **Sim stays the fixture.** Add a `disconnect` failure mode (raises `DeviceDisconnectedError`) so
  `E004` is exercisable with no hardware; the host classifies it.
- **Build order (pure units first, integrator last):** 5.1 policy → 5.2 identity → 5.3 watchdog →
  5.4 device-disconnect classification → 5.5 recorder gap/segment API → 5.6 supervisor →
  5.7 recorder write-failure → 5.8 integration + gate. (Maps to spec §5 tasks 5.1–5.5.)
- The cross-process degradation integration uses real child processes with generous timeouts; the
  pending **Linux multiprocessing validation** (README "Known follow-ups") still applies. Commands run
  via the venv interpreter; ruff exit code checked directly (not through a pipe).

### Task 5.1 — Restart backoff policy (pure)

**Files:** create `src/mmco/supervisor/__init__.py`, `src/mmco/supervisor/policy.py`,
`tests/supervisor/__init__.py`, `tests/supervisor/test_policy.py`. (Spec §6, task 5.4.)

A pure `RestartPolicy(base_s, cap_s)` with `backoff(attempt: int) -> float = min(base · 2^attempt,
cap)`. No max-attempts: a permanently-gone device keeps retrying at the cap interval.

- [ ] **Step 1 — Failing tests.** Assert: `backoff(0) == base_s`; it doubles per attempt
  (`backoff(1) == 2·base_s`, `backoff(2) == 4·base_s`); it is **capped** (`backoff(100) == cap_s`);
  and never exceeds `cap_s`.
- [ ] **Step 2 — RED.** `python -m pytest tests/supervisor/test_policy.py -v` → FAIL (`No module
  named 'mmco.supervisor'`).
- [ ] **Step 3 — Implement.** Add `src/mmco/supervisor/__init__.py` and `policy.py` with the pure
  `RestartPolicy`. Add empty `tests/supervisor/__init__.py`.
- [ ] **Step 4 — GREEN.** `python -m pytest tests/supervisor/test_policy.py -v` → pass.
- [ ] **Step 5 — Commit.** `Restart Policy: add capped exponential backoff`.

### Task 5.2 — Device identity resolver (pure)

**Files:** create `src/mmco/supervisor/identity.py`, `tests/supervisor/test_identity.py`.
(Spec §6, task 5.4.)

An `IdentityRegistry` mapping a stable device identity (by-id / `VID:PID:serial`) → `sensor_id`.
`register(sensor_id, identity)` and `resolve(identity) -> sensor_id`; resolution is by **identity
only**, independent of any transient device index.

- [ ] **Step 1 — Failing tests.** Assert: `resolve` returns the registered `sensor_id` for an
  identity; the **same identity presented with a different device index** still resolves to the same
  sensor (model the index as a separate, ignored field); an unknown identity raises `KeyError`.
- [ ] **Step 2 — RED.** `python -m pytest tests/supervisor/test_identity.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Add `identity.py` with the registry (dict identity → sensor_id).
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Device Identity: add stable-identity resolver`.

### Task 5.3 — Watchdog & health codes (deterministic)

**Files:** create `src/mmco/supervisor/watchdog.py`, `tests/supervisor/test_watchdog.py`.
(Spec §6, task 5.2.)

A `Watchdog` with `register(sensor_id, rate_hz, factor, floor_s)`, `note_event(sensor_id, now)`, and
`check(sensor_id, now, alive) -> ErrorCode | None`: returns `E002` if `not alive`; else `E003` if
`now - last_event > timeout` (`timeout = max(factor / rate_hz, floor_s)`); else `None`. Time is passed
in, so tests are deterministic.

- [ ] **Step 1 — Failing tests.** Assert: a dead process (`alive=False`) → `ErrorCode.DRIVER_CRASH`
  (`E002`); a live stream with no events past its timeout → `ErrorCode.WATCHDOG_TIMEOUT` (`E003`); a
  live stream that **kept emitting within the timeout** (a legitimately slow-but-alive stream) → `None`
  (not falsely killed); `note_event` resets the clock.
- [ ] **Step 2 — RED.** `python -m pytest tests/supervisor/test_watchdog.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Add `watchdog.py` (per-sensor last-event map + timeout math; no real
  sleeping).
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Watchdog: add per-stream crash/hang health detection`.

### Task 5.4 — Device-disconnect classification

**Files:** modify `src/mmco/core/driver.py` (add `DeviceDisconnectedError`),
`src/mmco/drivers/simulated.py` (add `disconnect` mode), `src/mmco/host/driver_host.py` (classify);
extend `tests/drivers/test_simulated.py`, `tests/host/test_driver_host.py`. (Spec §6, task 5.2.)

Add a `DeviceDisconnectedError` exception. The sim grows a `disconnect` failure mode (raises it after N
reads). The host maps a `DeviceDisconnectedError` from `read()` to a `LogEvent(code=E004)` while any
other exception stays `E002`.

- [ ] **Step 1 — Failing tests.** Sim: with `failure="disconnect", failure_after=2`, the third `read()`
  raises `DeviceDisconnectedError`. Host: a disconnect-mode sim makes the child emit a `LogEvent` with
  `ErrorCode.DEVICE_DISCONNECTED` (and still exit cleanly).
- [ ] **Step 2 — RED.** `python -m pytest tests/drivers/test_simulated.py tests/host/test_driver_host.py
  -v` → FAIL (new assertions).
- [ ] **Step 3 — Implement.** Add the exception + sim mode + host classification (catch
  `DeviceDisconnectedError` first → `E004`; generic `Exception` → `E002`).
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Device Disconnect: add sim disconnect mode and host E004 classification`.

### Task 5.5 — Recorder gap logging + multi-segment resume

**Files:** modify `src/mmco/record/manifest_author.py` (add `add_gap`), `src/mmco/record/recorder.py`
(gap + new-segment API); create `tests/record/test_recorder_gaps.py`. (Spec §5, §6, tasks 5.3/5.4.)

`ManifestAuthor.add_gap(sensor_id, gap)`. The `Recorder` gains `open_gap(sensor_id, start, end, reason,
code)` — closes the current writer, records its `Segment`, and appends the `Gap` — and resumes into a
**new segment** (incrementing `block_index`, new file `<sensor>-NNN.parquet`) on the next event.

- [ ] **Step 1 — Failing test.** Drive a recorder in-process: write a few tabular events, call
  `open_gap(...)` with a code, write a few more, stop. Assert the manifest has **two segments**
  (`block_index` 0 then 1) with **one gap** carrying the code between them, both parquet files exist,
  and the gap's `start/end` sit between the segments' times.
- [ ] **Step 2 — RED.** `python -m pytest tests/record/test_recorder_gaps.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Add `add_gap` to the author; in the recorder, track `block_index` per
  sensor, finalize-on-gap, and lazily open the next-indexed file on resume.
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Recorder: add gap logging and multi-segment resume`.

### Task 5.6 — Supervisor: spawn/monitor, shm ownership, degrade & restart

**Files:** create `src/mmco/supervisor/supervisor.py`, `tests/supervisor/test_supervisor.py`.
(Spec §3.1, §6, tasks 5.1/5.3/5.4.)

A `Supervisor` given per-sensor specs: on `start` it sweeps stale segments, creates a ring + queues +
channels per sensor, spawns each host, and registers each with the watchdog/identity. A `tick(now)`
drains every consumer into the `Recorder`, feeds `note_event`, runs `watchdog.check`, and on a
detection **opens a gap (coded) + emits a log + keeps the other streams running**, then **re-spawns**
the dead host per the backoff policy (re-binding by identity) so it resumes into a new segment. `stop`
requests stop on all hosts, joins them, writes the manifest, and `unlink`s every segment.

- [ ] **Step 1 — Failing test (real child processes).** Start a supervisor with **two** sims, one in
  `crash` mode. Pump `tick` for a bounded time, then `stop`. Assert: the manifest exists; the **healthy
  stream has a continuous (single) segment** and kept recording; the **crashed stream shows a gap with
  `ErrorCode.DRIVER_CRASH` and ≥ 2 segments** (resumed after re-spawn); a crash + reconnect `LogEvent`
  were aggregated; and **no child process or `mmco-*` segment is leaked** after `stop` (the
  segment-leak assertion is `skipif(win32)`).
- [ ] **Step 2 — RED.** `python -m pytest tests/supervisor/test_supervisor.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Add `supervisor.py` composing the per-sensor runtimes, the watchdog,
  identity, policy, and recorder; ensure clean teardown on every path.
- [ ] **Step 4 — GREEN.** pass (generous timeouts).
- [ ] **Step 5 — Commit.** `Supervisor: spawn/monitor hosts, own shm, degrade and restart`.

### Task 5.7 — Recorder write-failure policy (E007)

**Files:** modify `src/mmco/record/recorder.py` (catch writer errors); create
`tests/record/test_recorder_write_failure.py`. (Spec §5, task 5.5.)

A writer raising during `write_event`/`close` is caught by the recorder, which opens a coded gap
(`ErrorCode.WRITER_FAILURE`, `E007`) for that stream **without crashing**; other streams keep
recording.

- [ ] **Step 1 — Failing test.** Register a fake writer that raises on `write_event` for one sensor;
  drive the recorder with that sensor plus a healthy parquet sensor. Assert: the failing stream gets an
  `E007` gap, the recorder does **not** raise, and the healthy stream still records its events + segment.
- [ ] **Step 2 — RED.** `python -m pytest tests/record/test_recorder_write_failure.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Wrap writer calls in the recorder; on failure, open an `E007` gap and
  drop the broken writer (so the stream settles into a gap) without propagating.
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Recorder: treat writer failure as a coded gap (E007)`.

### Task 5.8 — Integration + Phase 5 gate

**Files:** create `tests/integration/test_degradation.py`.

- [ ] **Step 1 — Degradation integration test.** Two simulated sensors; mid-session one is killed
  (crash mode). Assert end-to-end via the manifest + logs: the killed stream shows **gap → new
  segment** with the right code and a reconnect log; the other stream is **uninterrupted**; the core
  never raised. (Generous timeouts; real child processes.)
- [ ] **Step 2 — Full suite + lint.** `python -m pytest` → all phases green (Linux-only checks skip on
  Windows); `python -m ruff check .` (verify exit `0`).
- [ ] **Step 3 — Update README.** Flip Phase 5 to ✅, Phase 6 to 🔜; refresh test count + stage line;
  note the resilience demo works (kill a sensor, session survives + auto-reconnects).
- [ ] **Step 4 — Commit.** `Docs: mark Phase 5 complete in progress README`.

**Files (Phase 5 total):** `src/mmco/supervisor/{__init__,policy,identity,watchdog,supervisor}.py`;
extensions to `core/driver.py`, `drivers/simulated.py`, `host/driver_host.py`,
`record/{manifest_author,recorder}.py`; `tests/supervisor/test_*.py`,
`tests/record/test_recorder_gaps.py`, `tests/record/test_recorder_write_failure.py`,
`tests/integration/test_degradation.py`.

**Outcome:** Kill/hang the simulated driver mid-session → other streams keep recording, gap + error code
are logged, the driver auto-reconnects (by stable identity) into a new segment. The resilience demo
(simulated). The core never crashes on a single stream's or the disk's failure.

---

## Phase 6 — Session log + auto-summary

**Goal:** Make the system self-documenting — every session leaves behind a machine-readable log of what
happened and a human-readable summary, with error codes that hint at any failures. This is the
"less documenting, less debugging" payoff.

**Branch:** `impl/phase-6-session-log` (off `master`, after Phase 5 merge).

**Design decisions (locked for this phase):**
- **The supervisor already aggregates `LogEvent`s** (`aggregated_logs`); Phase 6 just persists them and
  renders them. No new acquisition logic.
- **Session log = JSONL of the aggregated events**, in order, one `LogEvent.to_json()` per line. Pure
  stdlib (the model already round-trips). A `read_log` helper parses it back for the summary + tests.
- **Summary is generated purely from `manifest.json` + `session.log.jsonl`** — no hardware, no parquet
  reads. Per-stream it reports: type + nominal rate, segment count, captured span (first segment start
  → last segment end), an **approximate** sample count (`span_s × rate`, labelled approximate so it is
  not mistaken for an exact row count), and `dropped`. Gaps/reconnects are rendered in plain English
  with their `MMCO-Exxx` code + default message (from the `ErrorCode` taxonomy).
- **Cross-stream alignment** is reported modestly: the monotonic↔wall anchor is shown and a note says
  strict ±2 ms alignment validation lands with the webcam slice (Phase 9) — no overclaiming.
- The supervisor writes all three artifacts under `recordings/<session_id>/` using `mmco.paths`.
- **Build order:** 6.1 session log → 6.2 summary → 6.3 wire into the supervisor + integration → gate.
- Commands via the venv interpreter; ruff exit code checked directly.

### Task 6.1 — Session-log writer/reader

**Files:** create `src/mmco/record/session_log.py`, `tests/record/test_session_log.py`. (Spec §6.)

`write_log(path, events)` writes a list of `LogEvent`s to `session.log.jsonl` (one JSON object per
line, in order); `read_log(path) -> list[LogEvent]` parses it back.

- [ ] **Step 1 — Failing tests.** Under `tmp_path`: writing several `LogEvent`s (including ones
  carrying an `ErrorCode`) then `read_log` returns them **equal and in order**; the file has one line
  per event; an event's `code` survives the round-trip.
- [ ] **Step 2 — RED.** `python -m pytest tests/record/test_session_log.py -v` → FAIL (`No module named
  'mmco.record.session_log'`).
- [ ] **Step 3 — Implement.** Add `session_log.py` with `write_log`/`read_log` over
  `LogEvent.to_json`/`from_json`.
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Session Log: write and read session.log.jsonl`.

### Task 6.2 — Summary generator

**Files:** create `src/mmco/record/summary.py`, `tests/record/test_summary.py`. (Spec §6.)

`render_summary(manifest: SessionManifest, events: list[LogEvent]) -> str` builds the markdown;
`write_summary(session_dir) -> Path` reads `manifest.json` + `session.log.jsonl` from a session dir and
writes `summary.md`. The summary lists every stream (type, rate, segments, span, approx samples,
dropped) and renders each gap in plain English with its code + message.

- [ ] **Step 1 — Failing tests.** Build a `SessionManifest` with one stream that has a segment and a
  `Gap` coded `ErrorCode.DEVICE_DISCONNECTED`, plus a couple of `LogEvent`s. Assert `render_summary`:
  contains the `session_id` and the `sensor_id`; reflects the gap with **both** the code string
  (`MMCO-E004`) and its plain-English message (`device disconnected`); reports the segment count; and
  is produced from the objects alone (no I/O, no manual input). Then assert `write_summary(session_dir)`
  writes a non-empty `summary.md` that contains the same.
- [ ] **Step 2 — RED.** `python -m pytest tests/record/test_summary.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Add `summary.py` (`render_summary` pure; `write_summary` reads the two
  artifacts via `SessionManifest.from_json` + `read_log` and writes `summary.md`).
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Summary: generate human-readable summary.md from manifest + log`.

### Task 6.3 — Wire into the session lifecycle + integration

**Files:** modify `src/mmco/supervisor/supervisor.py` (write log + summary on stop); create
`tests/integration/test_self_documenting_session.py`. (Spec §6.)

`Supervisor.stop` already writes `manifest.json` (via the recorder). Extend it to also
`write_log(session_log_path, self.aggregated_logs)` and `write_summary(session_dir)` so every session
leaves all three artifacts.

- [ ] **Step 1 — Failing integration test.** Run a supervised session with a `disconnect`-mode sim (so
  a real fault occurs), stop, and assert: `manifest.json`, `session.log.jsonl`, and `summary.md` all
  exist under `recordings/<session_id>/`; `read_log` re-reads the log with the fault's code present; and
  the `summary.md` text names the injected fault's code (`MMCO-E004`) and its plain-English message.
- [ ] **Step 2 — RED.** `python -m pytest tests/integration/test_self_documenting_session.py -v` → FAIL.
- [ ] **Step 3 — Implement.** In `Supervisor.stop`, after the recorder writes the manifest, write the
  log and the summary into the session dir (paths from `mmco.paths`).
- [ ] **Step 4 — GREEN.** pass (generous timeouts; real child processes).
- [ ] **Step 5 — Commit.** `Supervisor: finalize manifest + log + summary on stop`.

### Task 6.4 — Phase 6 gate

- [ ] **Step 1 — Full suite + lint.** `python -m pytest` → all green (Linux-only checks skip on
  Windows); `python -m ruff check .` (verify exit `0`).
- [ ] **Step 2 — Update README.** Flip Phase 6 to ✅, Phase 7 to 🔜; refresh test count + stage line;
  note every session auto-produces manifest + log + summary.
- [ ] **Step 3 — Commit.** `Docs: mark Phase 6 complete in progress README`.

**Files (Phase 6 total):** `src/mmco/record/{session_log,summary}.py`; extension to
`supervisor/supervisor.py`; `tests/record/test_session_log.py`, `tests/record/test_summary.py`,
`tests/integration/test_self_documenting_session.py`.

**Outcome:** Every session auto-produces `manifest.json` + `session.log.jsonl` + `summary.md`. Inject a
fault → the summary names what failed in plain English with its error code. No hand-documentation.

---

## Phase 7 — Control surface: config, CLI, live status

**Goal:** Let an operator drive and observe the box.

**Branch:** `impl/phase-7-control-surface` (off `master`, after Phase 6 merge).

**Design decisions (locked for this phase):**
- **New runtime dependency: `PyYAML`** (config parsing). Added to `[project.dependencies]`; installed
  into the venv in Task 7.1.
- **Console entry point.** Add `[project.scripts]` `mmco = "mmco.cli.main:main"` so `mmco run …` works
  after `pip install -e .`. The CLI uses stdlib `argparse`.
- **Sim-only driver registry this phase.** The CLI maps a config's `driver` name to a builder that
  produces a `SensorSpec` (factory + driver config + capabilities). Only `"simulated"` is wired now; a
  general entry-point plugin registry (real drivers ship driver + writer together) is **Phase 8** — the
  registry here is a small dict, noted as the seam.
- **Single-process `run` with graceful finalize — detached `stop`/`status` deferred.** `mmco run`
  boots the supervisor, ticks the session, and **finalizes manifest + log + summary on completion or
  `KeyboardInterrupt`/`SIGINT`**. A *detached* `mmco stop` / `mmco status` against a separate running
  daemon needs an IPC channel (socket/pidfile) that is out of scope here; this is **flagged as a
  deviation** from the spec's task wording. For testability, `run` accepts a bounded duration. The
  status **renderer** is built and unit-tested now (and shown during `run`); the cross-process `status`
  *command* lands when the daemon/IPC arrives.
- **Build order:** 7.1 config → 7.2 profiles → 7.3 CLI run → 7.4 status renderer → 7.5 gate.
- Commands via the venv interpreter; ruff exit code checked directly.

### Task 7.1 — Config model + YAML loader

**Files:** modify `pyproject.toml` (add `PyYAML`); create `src/mmco/config/__init__.py`,
`src/mmco/config/config.py`, `tests/config/test_config.py`. (Spec §5.1, §7.)

`SensorConfig` (`id`, `driver`, `identity`, `rate_hz`, `protocol`, `profile_override: dict`) and
`SessionConfig` (`output_dir`, `sensors: list[SensorConfig]`, `recording_profiles: dict`). A
`ConfigError(Exception)` carrying `ErrorCode.CONFIG_INVALID`. `load_config(path) -> SessionConfig`
parses `sensors.yaml` with PyYAML and validates.

- [ ] **Step 1 — Add the dependency.** Add `PyYAML` to `[project.dependencies]`; run
  `python -m pip install -e ".[dev]"`.
- [ ] **Step 2 — Failing tests.** With a valid `sensors.yaml` written under `tmp_path`: `load_config`
  returns a `SessionConfig` with the expected `output_dir` and one `SensorConfig` (id/driver/rate
  populated, `profile_override` captured). A config missing a required field (e.g. a sensor with no
  `id`) raises `ConfigError` whose `.code is ErrorCode.CONFIG_INVALID`. Malformed YAML also raises
  `ConfigError`.
- [ ] **Step 3 — RED.** `python -m pytest tests/config/test_config.py -v` → FAIL (`No module named
  'mmco.config'`).
- [ ] **Step 4 — Implement.** Add `config/__init__.py`, `config/config.py` with the dataclasses,
  `ConfigError`, and `load_config` (PyYAML `safe_load`; validate required keys; wrap parse/validation
  errors as `ConfigError(code=E006)`).
- [ ] **Step 5 — GREEN.** pass.
- [ ] **Step 6 — Commit.** `Config: add session config model and YAML loader with E006 validation`.

### Task 7.2 — Recording-profile resolution

**Files:** create `src/mmco/config/profiles.py`, `tests/config/test_profiles.py`. (Spec §5.1.)

`resolve_profile(recording_profiles: dict, protocol: str, override: dict | None) -> dict` returns the
protocol's default profile merged with the per-sensor `override` (override wins per key; absent keys
fall back to the protocol default; unknown protocol → `override` alone or `{}`).

- [ ] **Step 1 — Failing tests.** Using the spec §5.1 example (`v4l2: {container: mp4, codec: h264,
  crf: 23}` …): the protocol default is applied when there is no override; a sensor's `crf: 18`
  override **beats** the default while the other keys (`container`, `codec`) fall back to the default;
  an unknown protocol with no override yields `{}`.
- [ ] **Step 2 — RED.** `python -m pytest tests/config/test_profiles.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Add `profiles.py` with the pure dict merge.
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Profiles: resolve recording profiles with per-sensor overrides`.

### Task 7.3 — CLI `run`

**Files:** create `src/mmco/cli/__init__.py`, `src/mmco/cli/main.py`, `tests/cli/test_run.py`.
(Spec §7.)

A small `simulated`-only driver registry maps a `SensorConfig` to a `SensorSpec`. `run_session(config,
*, max_seconds)` builds the specs, runs a `Supervisor` (tick loop bounded by `max_seconds`), and
finalizes on exit. `main(argv)` is the `argparse` entry point: `mmco run <config> [--seconds N]`.

- [ ] **Step 1 — Failing test.** Write a `sensors.yaml` with one `simulated` sensor under `tmp_path`;
  call `main(["run", str(cfg), "--seconds", "1"])` (or `run_session` directly). Assert the session
  finalized all three artifacts under `recordings/<session_id>/` (`manifest.json`, `session.log.jsonl`,
  `summary.md`) and that the process exited cleanly (real child sim host).
- [ ] **Step 2 — RED.** `python -m pytest tests/cli/test_run.py -v` → FAIL (`No module named
  'mmco.cli'`).
- [ ] **Step 3 — Implement.** Add `cli/__init__.py`, `cli/main.py` with the driver registry,
  `run_session`, and `main` (argparse subcommand `run`; graceful finalize on `KeyboardInterrupt`). Wire
  the `[project.scripts]` entry in `pyproject.toml`.
- [ ] **Step 4 — GREEN.** pass (generous bound).
- [ ] **Step 5 — Commit.** `CLI: add 'mmco run' to record a configured session`.

### Task 7.4 — Live status renderer

**Files:** create `src/mmco/cli/status_view.py`, `tests/cli/test_status_view.py`; extend
`src/mmco/supervisor/supervisor.py` with `snapshot()`. (Spec §7.)

`Supervisor.snapshot() -> list[dict]` reports per-sensor live counters (`sensor_id`, `alive`,
`dropped`, `reconnects`, `last_code`). `render_status(snapshot) -> str` renders a readable text table
(sensor, alive, dropped, reconnects, last error code).

- [ ] **Step 1 — Failing tests.** `render_status` of a fabricated snapshot (one healthy stream, one
  with a `last_code` of `MMCO-E004` and a reconnect) contains each sensor id, the dropped/reconnect
  counts, and the `MMCO-E004` code; an empty snapshot still renders a header without raising. Also: a
  started supervisor's `snapshot()` lists every sensor with the expected keys.
- [ ] **Step 2 — RED.** `python -m pytest tests/cli/test_status_view.py -v` → FAIL.
- [ ] **Step 3 — Implement.** Add `Supervisor.snapshot()`; add `status_view.py` with `render_status`.
  Have `run_session` print the table periodically (best-effort; not asserted).
- [ ] **Step 4 — GREEN.** pass.
- [ ] **Step 5 — Commit.** `Status View: render live per-sensor status table`.

### Task 7.5 — Phase 7 gate

- [ ] **Step 1 — Full suite + lint.** `python -m pytest` → all green (Linux-only checks skip on
  Windows); `python -m ruff check .` (verify exit `0`).
- [ ] **Step 2 — Update README.** Flip Phase 7 to ✅, Phase 8 to 🔜; refresh test count + stage line;
  note `mmco run sensors.yaml` records a configured session with a live status table.
- [ ] **Step 3 — Commit.** `Docs: mark Phase 7 complete in progress README`.

**Files (Phase 7 total):** `src/mmco/config/{__init__,config,profiles}.py`,
`src/mmco/cli/{__init__,main,status_view}.py`; extension to `supervisor/supervisor.py`;
`tests/config/test_*.py`, `tests/cli/test_*.py`.

**Outcome:** `mmco run sensors.yaml` records a configured session and finalizes all three artifacts,
printing a live status table; the status renderer reflects live per-sensor counters. (Detached
`mmco stop` / `mmco status` against a running daemon await the IPC channel — see decisions above.)

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

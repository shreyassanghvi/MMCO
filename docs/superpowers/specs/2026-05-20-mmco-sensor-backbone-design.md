# MMCO — Sensor-Coordination Backbone — Design Spec

- **Date:** 2026-05-20
- **Status:** Approved design, pre-implementation (revised after two-agent technical + coverage review)
- **Context:** Demo project for [Transfyr Bio](https://transfyr.ai/) (AIxBio, Cambridge MA),
  demonstrating founding-engineer-scope multimodal lab-capture infrastructure. Downstream consumer
  of recordings is an **ML training pipeline** learning from time-aligned video + audio + sensor
  traces of scientists at the bench.

> **Golden rule (see `CLAUDE.md`):** no implementation code is written at any stage without explicit
> user approval, and questions are asked whenever anything is in doubt. This document is design only.

---

## 1. Purpose & Scope

MMCO is the software backbone that runs on a capture box and coordinates whatever sensors are
plugged in — USB cameras, USB mics, IP cameras, serial IMUs, instrument log files. It is a wet-lab
analog to ROS 2 / NVIDIA Holoscan: a plugin architecture for sensor drivers, a unified timestamped
event bus, configurable recording profiles per protocol, and graceful degradation when a sensor
drops out. It ships as a containerized service and is the foundation other software projects depend
on.

This spec covers the **full architecture at a high level** plus the **one thin vertical slice built
first**. Additional drivers and capabilities follow the slice through the same plugin interface.

## 2. Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Implementation language | **Python core, native escape hatch** | ML pipeline downstream is Python; encoding hot paths are already native (ffmpeg/OpenCV); process-per-sensor sidesteps the GIL. Driver interface lets a Rust/C++ driver drop in later. |
| Concurrency / isolation | **Process-per-sensor + shared-memory bus** | Fault isolation: a hung/crashed driver cannot take down the bus or other sensors. This *is* the graceful-degradation mechanism. Parallelism without GIL contention. |
| Time alignment | **High-precision monotonic stamping, single host** | Stamp at acquisition against one monotonic clock; correct per-stream with a constant latency offset. Precision is sub-µs; absolute accuracy is bounded by acquisition jitter (see §4.2). |
| Recording format | **Per-stream native files + session manifest** | Native (mp4/wav/parquet) is maximally tool-friendly for ML loaders; the manifest carries timing/offsets/segments/gaps for alignment. |
| Degradation | **Keep recording, log gap, auto-reconnect** | Best resilience story for an unattended capture box. |
| Control surface | **YAML config + CLI + live status table** | Founding-engineer credible; no frontend rabbit hole; demos well in a terminal. |
| Runtime / dev env | **WSL2 / Linux for everything, containerized** | Faithful to "containerized service"; avoids Windows USB-in-Docker dead end. |
| Out-of-the-box | **One command + auto-detect sensors + simulated fallback** | `clone → one command → recording`, on real sensors if present, simulated if not. |
| Development method | **Test-driven (RED → GREEN → REFACTOR)** | Foundational component; correctness and regression-safety matter. Simulated driver is a first-class test fixture. |

## 3. Architecture

A **supervisor (core) process** plus **N isolated driver processes**, one per sensor. Drivers never
trust each other; the core never blocks on a driver.

```
                         ┌─────────────────────────────────────────────┐
                         │                CORE (supervisor)             │
   sensors.yaml ───────► │  • config loader OR auto-discovery           │
   (optional)            │  • default-session builder (+ sim fallback)  │
   CLI (run/stop/status) │  • driver supervisor (spawn/health/restart)  │
                  ───────►  • event bus consumer (drains ring buffers)  │
   live status table ◄── │  • recorder (writers + session manifest)     │
                         │  • clock reference + latency-offset registry │
                         │  • OWNS shared-memory lifecycle (create/unlink)│
                         └──────▲────────────▲────────────▲─────────────┘
                       shm ring + metadata queue + ctrl pipe (per driver)
                ┌─────────────┘      │             └──────────────┐
        ┌───────┴────────┐   ┌───────┴────────┐         ┌─────────┴────────┐
        │ DriverHost:cam │   │ DriverHost:mic │   ...   │ DriverHost:sim   │
        │ stamp@acquire  │   │ stamp@acquire  │         │ stamp@acquire    │
        └────────────────┘   └────────────────┘         └──────────────────┘
```

**Core is the trust boundary, and it is the system's single point of failure.** Driver faults are
isolated; a fault in the core (bus consumer, recorder, clock) ends the session. We accept this for a
single-host demo, keep the core small and well-tested, and give the recorder its own write-failure
policy (§6) so disk problems degrade gracefully rather than crash the core.

### 3.1 Components (each a small, independently testable unit)

1. **`SensorDriver` plugin interface** — abstract base every driver implements:
   `open() / read() → Event(s) / close()`, plus declared `capabilities` (stream type, rate, payload
   schema) and a `health()` heartbeat (§3.3). Drivers discovered via Python **entry points** *and* a
   config-declared registry, so third-party drivers drop in without touching the core. The exact
   `Event`/payload contract a driver author must satisfy is defined in §4.0.
2. **Driver host (process wrapper)** — generic runner that loads one driver, owns its acquisition
   loop, stamps events at acquisition, and **copies the driver-returned payload into the shared-memory
   ring** (the driver never touches shm directly — it just returns bytes/buffers; see §4.0). The same
   wrapper hosts every driver type.
3. **Event bus** — per-driver **shared-memory ring buffer** for payloads + a **metadata queue** for
   small records. Large frames travel through shared memory, never pickled across a pipe. **The core
   creates, owns, and `unlink()`s every ring segment** (drivers only attach by name) so a crashed
   driver never leaks shm; the core sweeps stale `mmco-*` segments on startup and manages Python's
   `resource_tracker` explicitly. Overflow and slot-reuse semantics are defined in §4.1. The bus
   consumer is internal to the recorder for the slice; a public subscribe API is future work (§11).
4. **Supervisor** — spawns drivers, monitors `health()`/liveness, and on crash/drop applies the
   degradation policy (mark gap → keep others alive → re-spawn with backoff → resume), keyed on
   **stable device identity** rather than `/dev` path (§6).
5. **Recorder** — pluggable per-stream writers (mp4/wav/parquet) + the session-manifest author.
   Writers are registered through the same plugin mechanism as drivers, so a new stream type ships
   its driver and its writer together.
6. **Clock & offset registry** — single monotonic reference; holds each sensor's measured/declared
   latency offset.
7. **Device discovery** — enumerates `/dev/video*` (V4L2), ALSA/Pulse capture devices, and
   `/dev/ttyUSB*` / `/dev/ttyACM*` serial ports; matches each to a capable driver and records its
   **stable identity** (by-id path / USB VID:PID:serial) for reconnect.
8. **Default-session builder** — if no `sensors.yaml` is supplied, builds a default session from
   discovery; if nothing is found, falls back to the built-in **simulated sensor** so a fresh clone
   always produces a recording. An explicit `sensors.yaml` always overrides discovery.
9. **Control surface** — YAML config loader, CLI (`run` / `stop` / `status`), and the live
   status renderer (sensors, rate/fps, dropped frames, reconnect events, last error code).

## 4. Data Flow & Timestamping

### 4.0 Event & payload contract (what a driver author must satisfy)

A `SensorDriver.read()` returns zero or more `Event`s. An `Event` carries:

- `payload`: raw bytes (or a buffer object exposing the buffer protocol) — the driver produces this;
  **the driver host copies it into the ring**. Drivers never allocate or write shared memory.
- `payload_schema_ref`: a reference to the stream's declared schema (from `capabilities`). Schemas are
  declared as a small typed descriptor: for `tabular`, an ordered list of `{name, dtype}` columns; for
  `video`, `{codec_or_raw, width, height, pixel_format}`; for `audio`, `{sample_rate, channels,
  sample_format}`.
- The host adds `sensor_id`, monotonic `seq`, and `t_acquire` (§4.1). Drivers do not set these.

The metadata record placed on the queue is `{ sensor_id, seq, t_acquire_ns, slot, length, gen }`
(`gen` = slot generation, see §4.1).

### 4.1 Steady-state flow (one sensor)
1. Driver host calls `driver.read()`; the instant data lands it takes
   `t_acquire = time.monotonic_ns()` and tags the event with sensor id + monotonic sequence number.
2. The host copies the payload into the next **ring slot** (recording its generation counter `gen`),
   then enqueues the metadata record `{id, seq, t_acquire, slot, length, gen}`.
3. The core's bus consumer drains metadata queues, reads the payload from `slot`, and **re-checks
   `gen` after the copy**; if the slot was overwritten (slow consumer), the event is counted as a drop
   rather than delivering corrupt data.
4. The recorder routes each event to its stream's writer and appends a per-block timing row to the
   in-progress manifest (§5).

**Backpressure / overflow policy.** Rings are non-blocking: if the ring is full, the producer
**drops the oldest** unconsumed slot and increments that stream's `dropped` counter. The core never
blocks on a driver (this is what makes the §3 guarantee true). Every drop is surfaced in the live
status table and recorded in the manifest (per-stream `dropped` count + the affected time range), so
the ML side can see exactly where data is missing instead of silently mis-aligning. Per-driver ring
slot size and count are sized from the stream's declared `capabilities` (a 4K video ring and an IMU
ring are sized independently).

### 4.2 Timestamping (precision vs. accuracy, single host)
- **Precision:** one monotonic clock reference for the whole box; every driver process stamps against
  the **same** clock source at acquisition. `time.monotonic_ns()` gives sub-microsecond resolution.
- **Accuracy is bounded by acquisition jitter, not by clock precision.** `t_acquire` is taken in
  Python *after* the driver's read returns, so USB/driver buffering, OS scheduling, and per-process
  GC pauses inject jitter between the physical event and the stamp. Process-per-sensor removes
  cross-sensor GIL contention but not these per-process effects. **We therefore claim high-precision
  monotonic stamping with constant per-stream offset correction; we do not claim guaranteed
  sub-millisecond absolute accuracy** unless an offset is calibrated (below).
- **Offset correction:** each sensor has a **latency offset** in the registry — a measured or declared
  constant for the driver+buffer delay. The manifest stores both raw `t_acquire` and corrected
  `t_event = t_acquire − offset`. Subtracting a constant removes mean bias; residual jitter remains.
- **Sampled streams (audio):** timestamps are derived from **sample-count × sample-rate** anchored to
  the stream's first `t_acquire`, not from per-buffer `t_acquire` — this is monotonic-by-construction
  and avoids buffer-arrival jitter.
- **Wall-clock anchor:** `CLOCK_REALTIME` captured once at session start alongside monotonic places
  sessions on absolute time without polluting per-event stamps. (Single anchor; over very long
  sessions NTP slew makes the absolute mapping drift — acceptable under the single-host scope, §10.)
- **Validation in the slice:** the integration test asserts cross-stream alignment within a concrete
  tolerance of **±2 ms** between the simulated stream and a reference; a coarse measured offset for the
  webcam is recorded rather than guessed. Full auto-calibration remains future work (§11).

## 5. Recording & Manifest

- **Per-stream native writers:** video → mp4/mkv (PyAV/ffmpeg), audio → wav/flac,
  IMU/serial → parquet (batched rows).
- **One `manifest.json` per session** — the contract the ML loader reads to align everything:
  - session id, monotonic↔wall anchor, output directory layout;
  - per-stream blocks:
    `{ sensor_id, type, capabilities, latency_offset, dropped, segments[], gaps[] }`
    where each **segment** is `{ file_path, start_timestamp, end_timestamp, block_index }` and each
    **gap** is `{ start, end, reason, code }`.
  - **`segments[]` (not a single `file_path`)** so a stream that disconnects and reconnects is
    represented as multiple files with the hole between them preserved as a gap — mp4/wav are not
    safely appendable mid-session.
  - **Per-block timestamps:** writers emit a sidecar of per-frame/per-block timestamps (e.g. parquet
    column of `t_event`, or an mp4 PTS→monotonic mapping table) rather than only first/last + rate,
    because real cameras don't deliver at exactly nominal fps and any drop breaks uniform spacing.

### 5.1 Recording profiles (configurable, per protocol)

Profiles are declared in `sensors.yaml` with **protocol-level defaults** and optional **per-sensor
overrides** (a per-sensor key wins over its protocol default). Example:

```yaml
recording_profiles:
  v4l2:                       # protocol default for all USB cameras
    container: mp4
    codec: h264
    crf: 23
    timestamp_sidecar: true
  alsa:
    container: wav
    sample_format: s16le
  serial:
    container: parquet
    batch_rows: 500

sensors:
  - id: bench_cam
    driver: webcam_v4l2
    identity: "usb-046d_HD_Pro_Webcam_C920-video-index0"
    profile_override:         # this camera only
      crf: 18                 # higher quality than the v4l2 default
```

The slice demonstrates at least one non-default profile (the `crf: 18` override above) so the
"configurable per protocol" requirement is exercised, not just specified.

## 6. Graceful Degradation & Auto-Reconnect

The supervisor watches each driver's liveness / `health()` heartbeat. On crash, hang, or
device-gone it:

1. Records a **gap** `{ start, end, reason, code }` in that stream's manifest block, where `code` is a
   generic error code (e.g. driver-crash, watchdog-timeout, device-disconnected).
2. Leaves all other streams recording untouched.
3. Tears down the dead driver process, **unlinks/recreates its shm segment** (core owns lifecycle,
   §3.3), and re-spawns it with exponential backoff up to a **cap**; a device gone for the rest of the
   session settles into the all-gap state rather than spin-looping.
4. On recovery the driver re-opens by **stable identity** (by-id / VID:PID:serial — *not* the old
   `/dev` index, which often changes on re-enumeration); the resumed data starts a **new segment**
   (§5) with the gap preserved between segments.

**Watchdog tuning.** The hang threshold is per-stream, derived from the declared `rate` in
`capabilities` (a 5 fps IP camera and a 200 Hz IMU have very different "too quiet" thresholds), so a
legitimately slow-but-alive stream is not killed and made to manufacture a false gap.

**Recorder-side failures.** A writer error or disk-full (`code = writer-failure`) is treated like a
stream fault: the affected stream's segment is closed and a gap opened, other streams keep recording,
and the condition is logged with its code — the recorder does not crash the core.

A sensor that is never available is simply a stream that is all-gap — never a failed session.

## 7. Out-of-the-Box Behavior (Linux)

- **One command:** `docker compose up` (or `mmco run`) boots the service with an auto-built default
  config — no hand-editing to get a first capture.
- **Auto-detect:** discovery enumerates cameras, mics, and serial ports and builds a default session.
- **Simulated fallback:** if no hardware is found, the simulated sensor guarantees an end-to-end
  recording.
- **Container device passthrough & persistence:** the compose file maps capture devices into the
  container (`devices: ["/dev/video0:/dev/video0", ...]`, plus the relevant `group_add`/udev for
  V4L2/ALSA/serial) and mounts a host volume at the recordings directory so output survives the
  container. Where dynamic device sets make explicit `devices:` mappings impractical, a documented
  privileged/`--device-cgroup-rule` fallback is provided. With **no devices mapped**, the container
  still records via the simulated fallback.
- **Reaching status when detached:** `mmco status` attaches to the running session over the control
  socket, so the live table works whether the service runs in the foreground or detached in the
  container.
- **Stock deps only:** V4L2 / ALSA / pyserial / ffmpeg via pip + apt; no exotic drivers or kernel
  modules. WSL2 host note: attaching USB devices to WSL2 first requires `usbipd-win`.

## 8. Thin Vertical Slice (Built First)

**Goal:** prove the whole backbone end-to-end with the fewest moving parts —
`clone → one command → aligned recording`, including a live degradation/reconnect moment.

**In scope**
- Core: config-loader-or-autodiscover → supervisor → shm bus → recorder → manifest →
  CLI `run` / `status` with live status table.
- **Two drivers:** the **simulated sensor** (always-on fallback, deterministic test fixture) and the
  **USB webcam** (V4L2). Together they exercise a tiny high-rate stream and a real heavy video stream.
- **One non-default recording profile** exercised (e.g. webcam `crf` override) so the per-protocol
  profile feature is demonstrated, not just specified.
- Degradation demo: kill/unplug the webcam mid-session → other stream keeps recording, gap + error
  code logged, auto-reconnect on return (by stable identity) into a new segment.
- One-command launch + simulated fallback when no camera is present.

**Out of scope (architecturally stubbed, drop in later via the plugin interface)**
- Mic, serial IMU, IP camera, instrument log-file drivers.
- MCAP single-container writer.
- ROS 2 packaging and a public live subscribe/publish bus API.
- Native (Rust/C++) driver.

## 9. Testing Strategy (TDD)

Every unit is built **RED → GREEN → REFACTOR**: failing test first, minimal code to pass, then clean
up. Build order is dictated by testability.

- **Unit:** plugin-interface contract, `Event`/schema contract, manifest schema (segments + gaps),
  offset math, drop accounting, ring-buffer read/write incl. **slot-generation re-check**.
- **Integration (no hardware):** full session with *only* the simulated driver; assert files +
  manifest produced, timestamps monotonic, **cross-stream alignment within ±2 ms**, drops surfaced.
  **Always-green CI path.**
- **Fault-injection:** simulated driver with injectable crash/hang/slow modes; assert the supervisor
  logs the gap with the right error code, keeps other streams alive, re-spawns with backoff, and
  resumes into a new segment. Includes a recorder write-failure injection.
- **Manual hardware checklist:** documented steps for the webcam on real Linux (incl. the
  `usbipd-win` attach note for WSL2). The webcam driver gets a fake-V4L2 seam for its unit tests,
  including a reconnect-on-different-index case.

**Suggested build order:** pure/in-process units (manifest, offset math, plugin/Event contract, ring
buffer + generation check) → supervisor + recorder against the simulated driver → real webcam driver.

## 10. Limitations

- The Python core is right for this demo's sensor mix, but **many simultaneous 4K streams** (high
  aggregate bandwidth, multiple parallel encoders) is the regime where moving the core/hot paths to
  **C++/Rust** pays off. The driver-interface seam is designed to allow that migration incrementally.
- **Absolute timing accuracy is bounded by uncalibrated acquisition jitter** (§4.2); the system
  guarantees high-precision monotonic stamping and constant-offset correction, not certified sub-ms
  absolute accuracy without calibration.
- The **core process is a single point of failure** (§3); driver faults are isolated, core faults are
  not.
- Single-host only; cross-host / networked clock discipline (PTP/NTP) is out of scope. The single
  wall-clock anchor drifts under NTP slew over very long sessions.

## 11. Future Work

- **ROS 2 package & public live bus API:** expose the event bus so streams publish as ROS 2 topics /
  run the backbone as a ROS 2 node with a subscribe/publish surface, making MMCO interoperable with
  the broader robotics ecosystem. To be brainstormed as its own sub-project.
- Additional drivers (mic, serial IMU, IP camera, instrument log files) via the plugin interface.
- MCAP writer backend selectable per recording profile.
- Optional native (Rust/C++/pybind11) driver to demonstrate the polyglot boundary.
- **Latency-offset auto-calibration** (loopback / flash-and-clap / hardware sync pulse) to substantiate
  sub-ms absolute accuracy, and multi-host time sync.
- A documented ML-loader/dataset contract (directory layout, manifest reader) for downstream consumers.
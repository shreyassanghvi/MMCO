# MMCO — Sensor-Coordination Backbone — Design Spec

- **Date:** 2026-05-20
- **Status:** Approved design, pre-implementation
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
| Time alignment | **Sub-millisecond, single host** | Stamp at acquisition against one monotonic clock; record per-sensor latency offsets. |
| Recording format | **Per-stream native files + session manifest** | Native (mp4/wav/parquet) is maximally tool-friendly for ML loaders; the manifest carries timing/offsets/gaps for alignment. |
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
                         └──────▲────────────▲────────────▲─────────────┘
                       shm ring + metadata queue + ctrl pipe (per driver)
                ┌─────────────┘      │             └──────────────┐
        ┌───────┴────────┐   ┌───────┴────────┐         ┌─────────┴────────┐
        │ DriverHost:cam │   │ DriverHost:mic │   ...   │ DriverHost:sim   │
        │ stamp@acquire  │   │ stamp@acquire  │         │ stamp@acquire    │
        └────────────────┘   └────────────────┘         └──────────────────┘
```

### 3.1 Components (each a small, independently testable unit)

1. **`SensorDriver` plugin interface** — abstract base every driver implements:
   `open() / read() → Event(s) / close()`, plus declared `capabilities` (stream type, rate, payload
   schema) and a `health()` signal. Drivers discovered via Python **entry points** *and* a
   config-declared registry, so third-party drivers drop in without touching the core.
2. **Driver host (process wrapper)** — generic runner that loads one driver, owns its acquisition
   loop, stamps events at acquisition, and pushes onto its outbound transport. The same wrapper
   hosts every driver type.
3. **Event bus** — per-driver **shared-memory ring buffer** for payloads + a **metadata queue** for
   small records. The core drains both. Large frames travel through shared memory, never pickled
   across a pipe.
4. **Supervisor** — spawns drivers, monitors `health()`/liveness, and on crash/drop applies the
   degradation policy (mark gap → keep others alive → re-spawn with backoff → resume).
5. **Recorder** — pluggable per-stream writers (mp4/wav/parquet) + the session-manifest author.
6. **Clock & offset registry** — single monotonic reference; holds each sensor's measured/declared
   latency offset.
7. **Device discovery** — enumerates `/dev/video*` (V4L2), ALSA/Pulse capture devices, and
   `/dev/ttyUSB*` / `/dev/ttyACM*` serial ports; matches each to a capable driver.
8. **Default-session builder** — if no `sensors.yaml` is supplied, builds a default session from
   discovery; if nothing is found, falls back to the built-in **simulated sensor** so a fresh clone
   always produces a recording. An explicit `sensors.yaml` always overrides discovery.
9. **Control surface** — YAML config loader, CLI (`run` / `stop` / `status`), and the live
   status renderer (sensors, rate/fps, dropped frames, reconnect events).

## 4. Data Flow & Timestamping

### 4.1 Steady-state flow (one sensor)
1. Driver host calls `driver.read()`; the instant data lands it takes
   `t_acquire = time.monotonic_ns()` and tags the event with sensor id + monotonic sequence number.
2. Payload → that sensor's **shared-memory ring buffer**; a small metadata record
   (id, seq, `t_acquire`, payload slot, byte length) → the **metadata queue**.
3. The core's bus consumer drains metadata queues, reads payloads from shared memory, and hands
   `(metadata, payload)` to the recorder.
4. The recorder routes each event to its stream's writer and appends a timing row to the in-progress
   manifest.

### 4.2 Timestamping (sub-ms, single host)
- One monotonic clock reference for the whole box; every driver process stamps against the **same**
  clock source at acquisition.
- Each sensor has a **latency offset** in the offset registry — a measured/declared constant for the
  driver+buffer delay between physical event and `t_acquire`.
- The manifest stores both raw `t_acquire` and corrected `t_event = t_acquire − offset`, so the ML
  side can choose.
- A wall-clock anchor (`CLOCK_REALTIME` captured once at session start alongside monotonic) places
  sessions on absolute time without polluting per-event stamps with wall-clock jitter.

## 5. Recording & Manifest

- **Per-stream native writers:** video → mp4/mkv (PyAV/ffmpeg), audio → wav/flac,
  IMU/serial → parquet (batched rows).
- **One `manifest.json` per session** — the contract the ML loader reads to align everything:
  - session id, monotonic↔wall anchor;
  - per-stream blocks: `{ sensor_id, type, file_path, sample_rate, latency_offset,
    first_timestamp, last_timestamp, gaps[] }`.
- **Recording profiles** are declared per sensor/protocol (container, codec/params, batching) and
  resolved at session start.

## 6. Graceful Degradation & Auto-Reconnect

The supervisor watches each driver's liveness / `health()`. On crash, hang (watchdog timeout), or
device-gone it:

1. Records a **gap** `{ start, end, reason }` in that stream's manifest block.
2. Leaves all other streams recording untouched.
3. Tears down the dead driver process and re-spawns it with backoff.
4. On recovery the driver re-opens the device and resumes; the new segment is stitched into the same
   stream with the gap preserved.

A sensor that is never available is simply a stream that is all-gap — never a failed session.

## 7. Out-of-the-Box Behavior (Linux)

- **One command:** `docker compose up` (or `mmco run`) boots the service with an auto-built default
  config — no hand-editing to get a first capture.
- **Auto-detect:** discovery enumerates cameras, mics, and serial ports and builds a default session.
- **Simulated fallback:** if no hardware is found, the simulated sensor guarantees an end-to-end
  recording.
- **Stock deps only:** V4L2 / ALSA / pyserial / ffmpeg via pip + apt; no exotic drivers or kernel
  modules. WSL2 note: attaching USB devices requires `usbipd-win`.

## 8. Thin Vertical Slice (Built First)

**Goal:** prove the whole backbone end-to-end with the fewest moving parts —
`clone → one command → aligned recording`, including a live degradation/reconnect moment.

**In scope**
- Core: config-loader-or-autodiscover → supervisor → shm bus → recorder → manifest →
  CLI `run` / `status` with live status table.
- **Two drivers:** the **simulated sensor** (always-on fallback, deterministic test fixture) and the
  **USB webcam** (V4L2). Together they exercise a tiny high-rate stream and a real heavy video stream.
- Degradation demo: kill/unplug the webcam mid-session → other stream keeps recording, gap logged,
  auto-reconnect on return.
- One-command launch + simulated fallback when no camera is present.

**Out of scope (architecturally stubbed, drop in later via the plugin interface)**
- Mic, serial IMU, IP camera, instrument log-file drivers.
- MCAP single-container writer.
- ROS 2 packaging.
- Native (Rust/C++) driver.

## 9. Testing Strategy (TDD)

Every unit is built **RED → GREEN → REFACTOR**: failing test first, minimal code to pass, then clean
up. Build order is dictated by testability.

- **Unit:** plugin-interface contract, manifest schema, offset math, gap recording, ring-buffer
  read/write.
- **Integration (no hardware):** full session with *only* the simulated driver; assert files +
  manifest produced, timestamps monotonic, alignment within tolerance. **Always-green CI path.**
- **Fault-injection:** simulated driver with injectable crash/hang/slow modes; assert the supervisor
  logs the gap, keeps other streams alive, and re-spawns with backoff.
- **Manual hardware checklist:** documented steps for the webcam on real Linux (incl. the
  `usbipd-win` attach note for WSL2). The webcam driver gets a fake-V4L2 seam for its unit tests.

**Suggested build order:** pure/in-process units (manifest, offset math, plugin contract, ring
buffer) → supervisor + recorder against the simulated driver → real webcam driver.

## 10. Limitations

- The Python core is right for this demo's sensor mix, but **many simultaneous 4K streams** (high
  aggregate bandwidth, multiple parallel encoders) is the regime where moving the core/hot paths to
  **C++/Rust** pays off. The driver-interface seam is designed to allow that migration incrementally.
- Single-host only; cross-host / networked clock discipline (PTP/NTP) is out of scope.

## 11. Future Work

- **ROS 2 package:** expose the event bus so streams publish as ROS 2 topics / run the backbone as a
  ROS 2 node, making MMCO interoperable with the broader robotics ecosystem. To be brainstormed as
  its own sub-project.
- Additional drivers (mic, serial IMU, IP camera, instrument log files) via the plugin interface.
- MCAP writer backend selectable per recording profile.
- Optional native (Rust/C++/pybind11) driver to demonstrate the polyglot boundary.
- Sub-ms latency-offset auto-calibration and multi-host time sync.

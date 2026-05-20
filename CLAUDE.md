# CLAUDE.md

## 🔒 GOLDEN RULE — NO CODING WITHOUT APPROVAL

**Do NOT write, edit, scaffold, or generate any implementation code at any stage without explicit user approval first.**

This applies to every stage of the project — design, planning, and implementation. Before producing any code (or running any command that creates/modifies source files), you MUST:

1. Present what you intend to build, in plain terms.
2. Wait for the user's explicit "yes / approved / go ahead."
3. Only then write code.

Design documents, specs, plans, and this kind of Markdown are allowed without code approval. Actual source code is not.

**Ask questions whenever in doubt.** Do not assume, guess, or fill gaps silently — at any stage (design, planning, implementation), if anything is ambiguous or underspecified, stop and ask the user before proceeding.

---

## Project: MMCO

A software backbone that runs on a capture box and coordinates whatever sensors are plugged in
(USB cameras, USB mics, IP cameras, serial IMUs, instrument log files). A wet-lab analog to ROS 2 /
NVIDIA Holoscan: a plugin architecture for sensor drivers, a unified timestamped event bus,
configurable recording profiles per protocol, and graceful degradation when a sensor drops out.
Ships as a containerized service. Foundational — other software projects depend on it.

### Decisions so far
- **Language:** Python core (3.14) for orchestration / bus / plugins; native (C/C++/Rust) hot paths
  added later only if profiling demands.
- **Design approach:** Full architecture at a high level, then build ONE thin end-to-end vertical
  slice first.
- **Dev hardware available:** USB webcam, USB/built-in mic, serial IMU/Arduino — plus a
  simulated/synthetic sensor driver so development is never blocked on hardware.

(Design spec lands in `docs/superpowers/specs/` once approved.)
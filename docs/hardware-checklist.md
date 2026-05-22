# MMCO Hardware Checklist — USB Webcam (V4L2)

Steps to run the **real** USB webcam path on Linux. Everything in the automated test suite is
hardware-free (the webcam driver uses a fake-capture backend, and the video writer encodes synthetic
frames), so this checklist is the only place real hardware is exercised. It is **manual**, not a test.

> Runtime target is Linux. On Windows, the webcam driver's `v4l2` backend is unavailable — develop and
> test against the fake backend, and run this checklist on Linux or WSL2.

## 1. Prerequisites

- A Linux host (native or WSL2) with a USB webcam.
- `ffmpeg` libraries available (the `av` wheel bundles them; if you build `av` from source, install
  `ffmpeg`/`libav*-dev` via apt first).
- The project installed: `python -m pip install -e ".[dev]"`.

## 2. Attaching the camera to WSL2 (Windows hosts only)

WSL2 does not see USB devices until they are attached with **`usbipd-win`**:

1. Install usbipd-win on Windows: `winget install usbipd`.
2. List devices (in an elevated Windows PowerShell): `usbipd list` — note the camera's `BUSID`.
3. Bind once: `usbipd bind --busid <BUSID>`.
4. Attach to WSL2: `usbipd attach --wsl --busid <BUSID>`.
5. Inside WSL2, confirm the node appears: `ls /dev/video*`.

Detach with `usbipd detach --busid <BUSID>` (or unplugging) to exercise the disconnect path.

## 3. Finding the camera's stable identity

The driver binds to a **stable identity**, not the transient `/dev/videoN` (which changes across
re-plugs). Find the by-id symlink:

```
ls -l /dev/v4l/by-id/
```

Use the `usb-...-video-index0` entry's path as the sensor `identity` in `sensors.yaml`. A reconnect
resolves the same identity to whatever `/dev/videoN` the camera comes back as.

## 4. Minimal config

```yaml
output_dir: .
recording_profiles:
  v4l2:
    container: mp4
    codec: libx264
    crf: 23
sensors:
  - id: cam0
    driver: webcam_v4l2
    identity: /dev/v4l/by-id/usb-<your-camera>-video-index0
    rate_hz: 30.0
    protocol: v4l2
    profile_override:
      crf: 18          # higher quality than the v4l2 default
```

Or skip the file entirely: `mmco run` auto-discovers `/dev/video*` and builds a default session
(falling back to the simulated sensor if no camera is found).

## 5. Recording

```
mmco run sensors.yaml --seconds 15
```

Expected:
- a live per-sensor status table prints each second;
- on completion, `recordings/<session_id>/` holds `manifest.json`, `cam0-000.mp4` and its
  `…​.mp4.timestamps.parquet` sidecar, `session.log.jsonl`, and `summary.md`.

## 6. Disconnect / reconnect demo

While recording, unplug the camera (or `usbipd detach`):
- the webcam stream logs a coded **`MMCO-E004`** gap and the recorder closes its current `.mp4` segment;
- any other stream keeps recording uninterrupted;
- on re-plug, the driver re-resolves the identity to the (possibly new) `/dev/videoN` and resumes into
  a **new** segment;
- the `summary.md` names the gap in plain English with its error code, and `manifest.json` shows two
  `cam0` segments with the gap between them.

## 7. Verifying alignment

Each stream's per-frame/per-row `t_event` lives in its sidecar (the mp4's
`…​.timestamps.parquet` for video, the parquet `t_event` column for tabular). All stamps share one
monotonic clock; declare each sensor's `latency_offset_ns` to correct constant device latency. The
automated `tests/integration/test_alignment.py` asserts offset-corrected streams align within ±2 ms.

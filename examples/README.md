# MMCO examples

A narrated, end-to-end demo of every MMCO feature. The default mode needs **no hardware and no
Docker** — it uses the simulated driver and the webcam's fake-capture backend.

## Run it (any OS)

```
pip install -e ".[dev]"
python examples/demo.py
```

You'll see two scenes:

- **Scene A — self-documenting session + live control channel.** Starts an unbounded `mmco run`
  session on a thread, queries it with **`mmco status`** over the loopback control channel, then
  **`mmco stop`** to finalize — and prints the resulting `manifest.json` (note the per-stream
  `latency_offset`) and the auto-generated `summary.md`.
- **Scene B — graceful degradation + video.** Records a simulated IMU and a webcam (real `mp4` +
  per-frame timestamp sidecar). The webcam "unplugs" mid-session: a coded **`MMCO-E004`** gap is
  logged, the IMU keeps recording, and the webcam **auto-reconnects by stable identity into a new
  mp4 segment** — visible as two `cam0-*.mp4` segments with the gap preserved between them.

It also prints the equivalent one-command CLI and `docker compose` invocations.

## Example config

[`sensors.yaml`](sensors.yaml) is a runnable config (`mmco run examples/sensors.yaml --seconds 10`)
showing recording profiles, a per-sensor `crf` override, and a declared `latency_offset_ns`. The
simulated sensor is active so it runs anywhere; a commented webcam block shows the real-camera setup.

## Real hardware (native Linux + a USB camera)

These modes validate the two open hardware follow-ups. **They need a real V4L2 node**, so run them on
a native Linux box (not WSL2 — its stock kernel has no `uvcvideo`/V4L2 driver, so `/dev/video0` never
appears even when the camera is forwarded with `usbipd`). USB attach to WSL/Linux: see
[`../docs/hardware-checklist.md`](../docs/hardware-checklist.md).

```
python examples/demo.py --discover        # enumerate real devices with stable identities  (issue #15)
python examples/demo.py --webcam -s 8      # auto-discover + record a real webcam for 8s    (issue #16)
```

- `--discover` prints each capture device with its stable `/dev/v4l/by-id/...` identity.
- `--webcam` auto-builds a session from discovery, records, and shows the real `mp4` + sidecar +
  manifest/summary. Unplug the camera mid-run to see the `E004` gap + reconnect live.

Capture that output to attach to issues
[#15](https://github.com/shreyassanghvi/MMCO/issues/15) and
[#16](https://github.com/shreyassanghvi/MMCO/issues/16).

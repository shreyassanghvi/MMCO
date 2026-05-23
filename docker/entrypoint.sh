#!/bin/sh
# Container entrypoint: record until the container is stopped (SIGTERM) or `mmco stop`.
# With no config and no mapped devices, `mmco run` auto-discovers and falls back to the simulated
# sensor, so the container always produces a recording. Extra args pass through.
set -e
exec mmco run "$@"

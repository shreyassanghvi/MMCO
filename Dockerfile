# MMCO capture-box service image.
# Records on startup (auto-discovery, simulated fallback) and serves a loopback control channel
# so `docker exec <c> mmco status` / `mmco stop` work on a detached container.
FROM python:3.14-slim

# System deps: ffmpeg for encoding + V4L2 device access, v4l-utils for camera tooling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user with a writable recordings directory (mounted as a volume in compose).
RUN useradd --create-home --uid 1000 mmco \
    && mkdir -p /data \
    && chown mmco:mmco /data

WORKDIR /app

# Install the package (metadata + source only; the wheel target packages src/mmco).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER mmco
ENV MMCO_OUTPUT_DIR=/data
# Records until the container is stopped (SIGTERM) or `mmco stop`.
CMD ["mmco", "run"]

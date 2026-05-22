"""Session configuration model and YAML loader (design spec §5.1, §7).

An operator describes a capture box in a ``sensors.yaml``: where to write, what recording profiles
each protocol uses, and the list of sensors to run. This module parses that file into typed
:class:`SessionConfig` / :class:`SensorConfig` values and validates it. Any parse or validation
failure surfaces as a :class:`ConfigError` carrying ``ErrorCode.CONFIG_INVALID`` (MMCO-E006), so a
bad config is reported with the same coded vocabulary as a runtime fault.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from mmco.core.errors import ErrorCode


class ConfigError(Exception):
    """A configuration is malformed or invalid; carries ``ErrorCode.CONFIG_INVALID``."""

    def __init__(self, message: str, *, code: ErrorCode = ErrorCode.CONFIG_INVALID) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SensorConfig:
    """One sensor entry from the config file."""

    id: str
    driver: str
    rate_hz: float
    identity: str | None = None
    protocol: str | None = None
    profile_override: dict = field(default_factory=dict)
    latency_offset_ns: int = 0


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """A whole capture session: output location, recording profiles, and sensors."""

    output_dir: str
    sensors: list[SensorConfig]
    recording_profiles: dict = field(default_factory=dict)


def _require(mapping: dict, key: str, where: str) -> object:
    if key not in mapping:
        raise ConfigError(f"{where}: missing required field {key!r}")
    return mapping[key]


def _parse_sensor(raw: object, index: int) -> SensorConfig:
    where = f"sensors[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: expected a mapping, got {type(raw).__name__}")
    override = raw.get("profile_override", {})
    if not isinstance(override, dict):
        raise ConfigError(f"{where}.profile_override: expected a mapping")
    return SensorConfig(
        id=str(_require(raw, "id", where)),
        driver=str(_require(raw, "driver", where)),
        rate_hz=float(_require(raw, "rate_hz", where)),
        identity=raw.get("identity"),
        protocol=raw.get("protocol"),
        profile_override=override,
        latency_offset_ns=int(raw.get("latency_offset_ns", 0)),
    )


def load_config(path: str) -> SessionConfig:
    """Parse and validate a ``sensors.yaml`` into a :class:`SessionConfig`.

    Raises :class:`ConfigError` (``MMCO-E006``) on malformed YAML, a non-mapping document, a
    missing required field, or a sensor entry of the wrong shape.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(f"malformed YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top-level document must be a mapping")

    sensors_raw = _require(raw, "sensors", path)
    if not isinstance(sensors_raw, list):
        raise ConfigError(f"{path}: 'sensors' must be a list")

    profiles = raw.get("recording_profiles", {})
    if not isinstance(profiles, dict):
        raise ConfigError(f"{path}: 'recording_profiles' must be a mapping")

    sensors = [_parse_sensor(entry, i) for i, entry in enumerate(sensors_raw)]
    return SessionConfig(
        output_dir=str(_require(raw, "output_dir", path)),
        sensors=sensors,
        recording_profiles=profiles,
    )

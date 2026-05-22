"""Default-session builder (design spec §3 component 8, §7).

Turns the output of :func:`~mmco.discovery.discovery.discover_devices` into a runnable
:class:`~mmco.config.config.SessionConfig` with no hand-editing. Each device kind maps to a driver
name and a sensible default rate/protocol; the resulting sensors are then **filtered to the set of
runnable drivers** (the CLI registry keys). Today only ``simulated`` is runnable, so discovered real
devices are reported by discovery but contribute no runnable sensor until their driver ships (webcam
in Phase 9) — the same builder picks them up automatically once that driver registers.

When the filter leaves nothing runnable, the builder falls back to a single simulated sensor so a
fresh clone always records (see :func:`build_default_session`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from mmco.config.config import SensorConfig, SessionConfig
from mmco.discovery.discovery import DeviceKind, DiscoveredDevice

SIMULATED_DRIVER = "simulated"
_SIM_RATE_HZ = 50.0


@dataclass(frozen=True, slots=True)
class _KindDefaults:
    driver: str
    rate_hz: float
    protocol: str


# Each discovered kind maps to the driver that runs it and sensible capture defaults. Only the
# drivers present in ``runnable_drivers`` actually produce a sensor (see build_default_session).
_KIND_DEFAULTS: dict[DeviceKind, _KindDefaults] = {
    DeviceKind.VIDEO: _KindDefaults(driver="webcam_v4l2", rate_hz=30.0, protocol="v4l2"),
    DeviceKind.AUDIO: _KindDefaults(driver="alsa_mic", rate_hz=48000.0, protocol="alsa"),
    DeviceKind.SERIAL: _KindDefaults(driver="serial_imu", rate_hz=100.0, protocol="serial"),
}


def _sensor_for(device: DiscoveredDevice, index: int) -> SensorConfig:
    defaults = _KIND_DEFAULTS[device.kind]
    return SensorConfig(
        id=f"{device.kind.value}{index}",
        driver=defaults.driver,
        rate_hz=defaults.rate_hz,
        identity=device.identity,
        protocol=defaults.protocol,
    )


def build_default_session(
    devices: Iterable[DiscoveredDevice],
    *,
    output_dir: str,
    runnable_drivers: set[str],
) -> SessionConfig:
    """Build a runnable session from discovered ``devices``, keeping only runnable drivers."""
    sensors: list[SensorConfig] = []
    for index, device in enumerate(devices):
        sensor = _sensor_for(device, index)
        if sensor.driver in runnable_drivers:
            sensors.append(sensor)
    if not sensors:
        sensors.append(_simulated_sensor())
    return SessionConfig(output_dir=output_dir, sensors=sensors)


def _simulated_sensor() -> SensorConfig:
    """The always-available fallback so a fresh clone records even with no runnable hardware."""
    return SensorConfig(
        id="sim0",
        driver=SIMULATED_DRIVER,
        rate_hz=_SIM_RATE_HZ,
        identity="sim0",
        protocol="simulated",
    )

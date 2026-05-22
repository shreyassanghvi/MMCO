"""Tests for the session config model and YAML loader (Task 7.1)."""

from __future__ import annotations

import pytest

from mmco.config.config import ConfigError, SessionConfig, load_config
from mmco.core.errors import ErrorCode

_VALID_YAML = """
output_dir: recordings
recording_profiles:
  v4l2:
    container: mp4
    codec: h264
    crf: 23
sensors:
  - id: cam0
    driver: simulated
    identity: usb-cam0
    rate_hz: 30.0
    protocol: v4l2
    profile_override:
      crf: 18
"""


def test_load_config_parses_valid_yaml(tmp_path):
    cfg_path = tmp_path / "sensors.yaml"
    cfg_path.write_text(_VALID_YAML)

    config = load_config(str(cfg_path))

    assert isinstance(config, SessionConfig)
    assert config.output_dir == "recordings"
    assert len(config.sensors) == 1
    sensor = config.sensors[0]
    assert sensor.id == "cam0"
    assert sensor.driver == "simulated"
    assert sensor.identity == "usb-cam0"
    assert sensor.rate_hz == 30.0
    assert sensor.protocol == "v4l2"
    assert sensor.profile_override == {"crf": 18}
    assert config.recording_profiles["v4l2"]["codec"] == "h264"


def test_load_config_missing_required_field_raises_e006(tmp_path):
    cfg_path = tmp_path / "sensors.yaml"
    cfg_path.write_text(
        "output_dir: recordings\n"
        "sensors:\n"
        "  - driver: simulated\n"  # no id
        "    rate_hz: 30.0\n"
    )

    with pytest.raises(ConfigError) as excinfo:
        load_config(str(cfg_path))
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID


def test_load_config_malformed_yaml_raises_e006(tmp_path):
    cfg_path = tmp_path / "sensors.yaml"
    cfg_path.write_text("output_dir: recordings\n  : : not valid : :\n")

    with pytest.raises(ConfigError) as excinfo:
        load_config(str(cfg_path))
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID

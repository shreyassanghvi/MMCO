"""Tests for recording-profile resolution (Task 7.2)."""

from __future__ import annotations

from mmco.config.profiles import resolve_profile

_PROFILES = {
    "v4l2": {"container": "mp4", "codec": "h264", "crf": 23},
    "alsa": {"container": "wav", "sample_rate": 48000},
}


def test_protocol_default_applied_without_override():
    assert resolve_profile(_PROFILES, "v4l2", None) == {
        "container": "mp4",
        "codec": "h264",
        "crf": 23,
    }


def test_override_beats_default_other_keys_fall_back():
    resolved = resolve_profile(_PROFILES, "v4l2", {"crf": 18})
    assert resolved == {"container": "mp4", "codec": "h264", "crf": 18}


def test_unknown_protocol_without_override_yields_empty():
    assert resolve_profile(_PROFILES, "unknown", None) == {}


def test_unknown_protocol_with_override_yields_override_alone():
    assert resolve_profile(_PROFILES, "unknown", {"crf": 10}) == {"crf": 10}

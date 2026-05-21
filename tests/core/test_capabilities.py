import pytest

from mmco.core.capabilities import (
    AudioSchema,
    Capabilities,
    Column,
    StreamType,
    TabularSchema,
    VideoSchema,
)


def test_tabular_schema_round_trips_and_preserves_column_order():
    schema = TabularSchema(
        columns=(
            Column(name="t_event", dtype="int64"),
            Column(name="ax", dtype="float32"),
            Column(name="ay", dtype="float32"),
        )
    )
    restored = TabularSchema.from_dict(schema.to_dict())
    assert restored == schema
    assert [c.name for c in restored.columns] == ["t_event", "ax", "ay"]


def test_video_schema_round_trips():
    schema = VideoSchema(
        codec_or_raw="raw", width=1280, height=720, pixel_format="yuyv422"
    )
    assert VideoSchema.from_dict(schema.to_dict()) == schema


def test_audio_schema_round_trips():
    schema = AudioSchema(sample_rate=48_000, channels=2, sample_format="s16le")
    assert AudioSchema.from_dict(schema.to_dict()) == schema


def test_capabilities_accepts_matching_type_and_schema():
    caps = Capabilities(
        type=StreamType.VIDEO,
        rate=30.0,
        schema=VideoSchema(
            codec_or_raw="raw", width=640, height=480, pixel_format="yuyv422"
        ),
    )
    assert caps.type is StreamType.VIDEO


def test_capabilities_rejects_mismatched_type_and_schema():
    with pytest.raises(ValueError):
        Capabilities(
            type=StreamType.VIDEO,
            rate=None,
            schema=AudioSchema(sample_rate=48_000, channels=1, sample_format="s16le"),
        )


def test_empty_tabular_schema_is_rejected():
    with pytest.raises(ValueError):
        TabularSchema(columns=())


def test_capabilities_round_trips_for_each_stream_type():
    cases = [
        Capabilities(
            type=StreamType.VIDEO,
            rate=30.0,
            schema=VideoSchema(
                codec_or_raw="raw", width=640, height=480, pixel_format="yuyv422"
            ),
        ),
        Capabilities(
            type=StreamType.AUDIO,
            rate=None,
            schema=AudioSchema(sample_rate=48_000, channels=2, sample_format="s16le"),
        ),
        Capabilities(
            type=StreamType.TABULAR,
            rate=100.0,
            schema=TabularSchema(columns=(Column(name="ax", dtype="float32"),)),
        ),
    ]
    for caps in cases:
        assert Capabilities.from_dict(caps.to_dict()) == caps

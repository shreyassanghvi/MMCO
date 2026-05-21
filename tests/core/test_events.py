import pytest

from mmco.core.events import DriverSample, EventMeta, SensorEvent


def test_driver_sample_holds_payload_and_schema_and_compares_by_value():
    a = DriverSample(payload=b"\x01\x02", payload_schema_ref="imu.v1")
    b = DriverSample(payload=b"\x01\x02", payload_schema_ref="imu.v1")
    assert a == b
    assert a.payload == b"\x01\x02"
    assert a.payload_schema_ref == "imu.v1"


def test_from_sample_copies_driver_fields_and_sets_host_fields():
    sample = DriverSample(payload=b"frame", payload_schema_ref="video.raw")
    event = SensorEvent.from_sample(
        sample, sensor_id="cam0", seq=7, t_acquire_ns=1_000
    )
    # driver-set fields carried over
    assert event.payload == b"frame"
    assert event.payload_schema_ref == "video.raw"
    # host-set fields applied
    assert event.sensor_id == "cam0"
    assert event.seq == 7
    assert event.t_acquire_ns == 1_000


def test_event_meta_constructs_and_compares_by_value():
    m1 = EventMeta(
        sensor_id="cam0", seq=3, t_acquire_ns=500, slot=2, length=128, gen=1
    )
    m2 = EventMeta(
        sensor_id="cam0", seq=3, t_acquire_ns=500, slot=2, length=128, gen=1
    )
    assert m1 == m2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sensor_id": "", "seq": 0, "t_acquire_ns": 0, "slot": 0, "length": 0, "gen": 0},
        {"sensor_id": "c", "seq": -1, "t_acquire_ns": 0, "slot": 0, "length": 0, "gen": 0},
        {"sensor_id": "c", "seq": 0, "t_acquire_ns": -1, "slot": 0, "length": 0, "gen": 0},
        {"sensor_id": "c", "seq": 0, "t_acquire_ns": 0, "slot": -1, "length": 0, "gen": 0},
        {"sensor_id": "c", "seq": 0, "t_acquire_ns": 0, "slot": 0, "length": -1, "gen": 0},
        {"sensor_id": "c", "seq": 0, "t_acquire_ns": 0, "slot": 0, "length": 0, "gen": -1},
    ],
)
def test_event_meta_rejects_invalid_fields(kwargs):
    with pytest.raises(ValueError):
        EventMeta(**kwargs)


def test_sensor_event_rejects_invalid_host_fields():
    sample = DriverSample(payload=b"x", payload_schema_ref="s")
    with pytest.raises(ValueError):
        SensorEvent.from_sample(sample, sensor_id="", seq=0, t_acquire_ns=0)
    with pytest.raises(ValueError):
        SensorEvent.from_sample(sample, sensor_id="c", seq=-1, t_acquire_ns=0)

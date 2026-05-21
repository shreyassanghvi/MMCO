import pytest

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.core.driver import DriverHealth, SensorDriver
from mmco.core.events import DriverSample


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=100.0,
        schema=TabularSchema(columns=(Column(name="v", dtype="float32"),)),
    )


class FakeDriver(SensorDriver):
    def open(self) -> None:
        self.opened = True

    def read(self) -> DriverSample:
        return DriverSample(payload=b"row", payload_schema_ref="imu.v1")

    def close(self) -> None:
        self.opened = False

    @property
    def capabilities(self) -> Capabilities:
        return _caps()

    def health(self) -> DriverHealth:
        return DriverHealth.OK


class IncompleteDriver(SensorDriver):
    # Deliberately omits read(), close(), capabilities, health().
    def open(self) -> None:
        pass


def test_sensor_driver_is_abstract_and_cannot_be_instantiated():
    with pytest.raises(TypeError):
        SensorDriver()


def test_complete_subclass_satisfies_the_contract():
    driver = FakeDriver()
    driver.open()
    sample = driver.read()
    assert isinstance(sample, DriverSample)
    assert isinstance(driver.capabilities, Capabilities)
    assert driver.health() is DriverHealth.OK
    driver.close()


def test_subclass_missing_abstract_methods_cannot_be_instantiated():
    with pytest.raises(TypeError):
        IncompleteDriver()

import struct
import threading
import time

import pytest

from mmco.core.capabilities import StreamType
from mmco.core.driver import DriverHealth
from mmco.drivers.simulated import SimConfig, SimulatedDriver


def _decode(payload: bytes) -> int:
    return struct.unpack("<q", payload)[0]


def test_capabilities_are_tabular_at_configured_rate():
    driver = SimulatedDriver(SimConfig(sensor_id="sim0", rate_hz=100.0))
    caps = driver.capabilities
    assert caps.type is StreamType.TABULAR
    assert caps.rate == 100.0
    assert len(caps.schema.columns) == 1
    assert driver.health() is DriverHealth.OK


def test_reads_return_strictly_increasing_counter():
    driver = SimulatedDriver(SimConfig(sensor_id="sim0", rate_hz=100.0))
    driver.open()
    values = [_decode(driver.read().payload) for _ in range(4)]
    assert values == [0, 1, 2, 3]


def test_crash_mode_raises_after_n_reads():
    driver = SimulatedDriver(
        SimConfig(sensor_id="sim0", rate_hz=100.0, failure="crash", failure_after=3)
    )
    driver.open()
    for _ in range(3):
        driver.read()  # first three succeed
    with pytest.raises(RuntimeError):
        driver.read()  # fourth raises


def test_slow_mode_delays_each_read():
    delay = 0.05
    driver = SimulatedDriver(
        SimConfig(sensor_id="sim0", rate_hz=100.0, failure="slow", delay_s=delay)
    )
    driver.open()
    start = time.monotonic()
    driver.read()
    assert time.monotonic() - start >= delay


def test_hang_mode_blocks_until_close_releases():
    driver = SimulatedDriver(
        SimConfig(sensor_id="sim0", rate_hz=100.0, failure="hang")
    )
    driver.open()
    done = threading.Event()

    def _worker():
        driver.read()
        done.set()

    t = threading.Thread(target=_worker)
    t.start()
    try:
        assert not done.wait(timeout=0.2)  # still blocked in read()
        driver.close()  # releases the hang
        assert done.wait(timeout=1.0)  # read() returns, worker finishes
    finally:
        t.join(timeout=1.0)
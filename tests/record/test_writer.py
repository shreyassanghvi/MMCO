import pytest

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.record import writer as writer_mod
from mmco.record.writer import StreamWriter, register_writer, writer_for


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=10.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


class FakeWriter(StreamWriter):
    def open(self) -> None:
        self.opened = True

    def write_event(self, t_event_ns: int, payload: bytes) -> None:
        self._observe(t_event_ns)

    def close(self) -> None:
        self.opened = False


@pytest.fixture
def isolated_registry():
    saved = dict(writer_mod._REGISTRY)
    try:
        yield
    finally:
        writer_mod._REGISTRY.clear()
        writer_mod._REGISTRY.update(saved)


def test_stream_writer_is_abstract():
    with pytest.raises(TypeError):
        StreamWriter(capabilities=_caps(), file_path="x.parquet")


def test_factory_returns_registered_writer(isolated_registry):
    register_writer(StreamType.TABULAR, FakeWriter)
    w = writer_for(StreamType.TABULAR, capabilities=_caps(), file_path="x.parquet")
    assert isinstance(w, FakeWriter)
    assert w.file_path == "x.parquet"


def test_factory_raises_for_unregistered_type(isolated_registry):
    writer_mod._REGISTRY.clear()
    with pytest.raises((KeyError, ValueError)):
        writer_for(StreamType.VIDEO, capabilities=_caps(), file_path="x")


def test_observes_first_and_last_timestamp(isolated_registry):
    register_writer(StreamType.TABULAR, FakeWriter)
    w = writer_for(StreamType.TABULAR, capabilities=_caps(), file_path="x")
    w.open()
    for t in (100, 200, 300):
        w.write_event(t, b"")
    w.close()
    assert w.start_timestamp == 100
    assert w.end_timestamp == 300

import struct

import pyarrow.parquet as pq

from mmco.core.capabilities import Capabilities, Column, StreamType, TabularSchema
from mmco.record.parquet_writer import ParquetWriter
from mmco.record.writer import writer_for


def _caps() -> Capabilities:
    return Capabilities(
        type=StreamType.TABULAR,
        rate=10.0,
        schema=TabularSchema(columns=(Column(name="n", dtype="int64"),)),
    )


def test_parquet_writer_writes_rows_with_t_event_column(tmp_path):
    path = str(tmp_path / "imu0.parquet")
    writer = ParquetWriter(capabilities=_caps(), file_path=path)
    writer.open()
    timestamps = [100, 200, 300]
    values = [7, 8, 9]
    for t, v in zip(timestamps, values, strict=True):
        writer.write_event(t, struct.pack("<q", v))
    writer.close()

    table = pq.read_table(path)
    assert table.num_rows == 3
    assert table.column("t_event").to_pylist() == timestamps
    assert table.column("n").to_pylist() == values


def test_parquet_writer_tracks_first_and_last_timestamp(tmp_path):
    path = str(tmp_path / "imu0.parquet")
    writer = ParquetWriter(capabilities=_caps(), file_path=path)
    writer.open()
    for t, v in zip([10, 20, 30], [1, 2, 3], strict=True):
        writer.write_event(t, struct.pack("<q", v))
    writer.close()
    assert writer.start_timestamp == 10
    assert writer.end_timestamp == 30


def test_parquet_writer_is_registered_for_tabular(tmp_path):
    writer = writer_for(
        StreamType.TABULAR, capabilities=_caps(), file_path=str(tmp_path / "x.parquet")
    )
    assert isinstance(writer, ParquetWriter)

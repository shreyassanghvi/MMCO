"""Parquet writer for tabular streams (design spec §5, §5.1).

Tabular payloads are rows whose values are ``struct``-packed in ``TabularSchema`` column order. This
writer derives both a ``struct`` format and an Arrow schema from the column dtypes, buffers decoded
rows, and on ``close`` writes a parquet file whose columns are ``t_event`` (the corrected per-row
timestamp) followed by the schema columns. The per-row ``t_event`` *is* the timestamp sidecar.
"""

from __future__ import annotations

import struct

import pyarrow as pa
import pyarrow.parquet as pq

from mmco.core.capabilities import Capabilities, StreamType
from mmco.record.writer import StreamWriter, register_writer

# dtype -> (struct format code, Arrow type)
_DTYPES: dict[str, tuple[str, pa.DataType]] = {
    "int64": ("q", pa.int64()),
    "int32": ("i", pa.int32()),
    "float64": ("d", pa.float64()),
    "float32": ("f", pa.float32()),
}


class ParquetWriter(StreamWriter):
    """Batches tabular rows to a parquet file with a per-row ``t_event`` column."""

    def __init__(self, *, capabilities: Capabilities, file_path: str, profile: dict | None = None):
        super().__init__(capabilities=capabilities, file_path=file_path, profile=profile)
        columns = capabilities.schema.columns
        self._names = [c.name for c in columns]
        self._arrow_types = [_DTYPES[c.dtype][1] for c in columns]
        self._struct = struct.Struct("<" + "".join(_DTYPES[c.dtype][0] for c in columns))
        self._t_events: list[int] = []
        self._rows: list[list] = [[] for _ in columns]

    def open(self) -> None:
        self._t_events = []
        self._rows = [[] for _ in self._names]

    def write_event(self, t_event_ns: int, payload: bytes) -> None:
        values = self._struct.unpack(payload)
        self._observe(t_event_ns)
        self._t_events.append(t_event_ns)
        for column, value in zip(self._rows, values, strict=True):
            column.append(value)

    def close(self) -> None:
        arrays = [pa.array(self._t_events, type=pa.int64())]
        names = ["t_event"]
        for name, arrow_type, column in zip(
            self._names, self._arrow_types, self._rows, strict=True
        ):
            arrays.append(pa.array(column, type=arrow_type))
            names.append(name)
        table = pa.Table.from_arrays(arrays, names=names)
        pq.write_table(table, self._file_path)


register_writer(StreamType.TABULAR, ParquetWriter)

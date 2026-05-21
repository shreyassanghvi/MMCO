"""Recording: turn drained events into per-stream files plus a session manifest.

A ``StreamWriter`` is selected per stream type and writes a native file (parquet for tabular
streams) carrying a per-row ``t_event``. The ``Recorder`` routes bus events to writers and drives
the ``ManifestAuthor``, which writes the ``manifest.json`` an ML loader reads to align everything.
"""

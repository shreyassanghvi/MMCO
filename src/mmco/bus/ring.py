"""Shared-memory payload ring (design spec §3.1, §4.1).

A fixed-size round-robin store over ``multiprocessing.shared_memory``. The producer ``write()``s a
payload into the next slot (overwriting the oldest — it never blocks) and gets back a
:class:`SlotRef` ``(slot, gen, length)``. A consumer reads a slot by that ref via ``read_slot()``;
``gen`` is a per-slot generation counter that lets the consumer detect a slot that was overwritten
before/during its read (a *lapped* slot) and reject it rather than return torn bytes.

The **ordering authority is the metadata queue**, not this ring — the ring is random-access storage
keyed by ``(slot, gen)``. Segment layout (stdlib ``struct``, little-endian, no padding)::

    header : magic(u32) n_slots(u32) slot_size(u32) write_idx(u64)
    slots  : n_slots × (gen(u64) length(u64))
    data   : n_slots × slot_size bytes

The **core owns the segment** (``create`` → ``unlink``); drivers ``attach`` by name and never
unlink.
"""

from __future__ import annotations

import os
import struct
import uuid
from dataclasses import dataclass
from multiprocessing import shared_memory

_MAGIC = 0x4D4D434F  # "MMCO"
_SEGMENT_PREFIX = "mmco-"

_HEADER = struct.Struct("<IIIQ")  # magic, n_slots, slot_size, write_idx
_SLOT = struct.Struct("<QQ")  # gen, length
_OFF_WRITE_IDX = 12  # byte offset of write_idx within the header


@dataclass(frozen=True, slots=True)
class SlotRef:
    """A reference to one written payload: its slot, the slot's generation, and byte length."""

    slot: int
    gen: int
    length: int


class RingBuffer:
    """A shared-memory round-robin payload store with generation-checked reads."""

    def __init__(self, shm: shared_memory.SharedMemory, n_slots: int, slot_size: int, owner: bool):
        self._shm = shm
        self._buf = shm.buf
        self._n_slots = n_slots
        self._slot_size = slot_size
        self._owner = owner
        self._slot_table_off = _HEADER.size
        self._data_off = _HEADER.size + n_slots * _SLOT.size

    # -- construction -------------------------------------------------------
    @classmethod
    def create(cls, n_slots: int, slot_size: int) -> RingBuffer:
        """Create and own a new segment, zero-initialised."""
        size = _HEADER.size + n_slots * _SLOT.size + n_slots * slot_size
        name = f"{_SEGMENT_PREFIX}{uuid.uuid4().hex[:16]}"
        shm = shared_memory.SharedMemory(create=True, size=size, name=name)
        # zero the header + slot table so gens/lengths/write_idx start at 0
        shm.buf[: _HEADER.size + n_slots * _SLOT.size] = bytes(
            _HEADER.size + n_slots * _SLOT.size
        )
        _HEADER.pack_into(shm.buf, 0, _MAGIC, n_slots, slot_size, 0)
        return cls(shm, n_slots, slot_size, owner=True)

    @classmethod
    def attach(cls, name: str, n_slots: int, slot_size: int) -> RingBuffer:
        """Attach to an existing segment by name without owning it."""
        shm = shared_memory.SharedMemory(name=name)
        return cls(shm, n_slots, slot_size, owner=False)

    @property
    def name(self) -> str:
        return self._shm.name

    # -- internal accessors -------------------------------------------------
    def _read_write_idx(self) -> int:
        return struct.unpack_from("<Q", self._buf, _OFF_WRITE_IDX)[0]

    def _set_write_idx(self, value: int) -> None:
        struct.pack_into("<Q", self._buf, _OFF_WRITE_IDX, value)

    def _slot_off(self, slot: int) -> int:
        return self._slot_table_off + slot * _SLOT.size

    def _read_slot_header(self, slot: int) -> tuple[int, int]:
        return _SLOT.unpack_from(self._buf, self._slot_off(slot))

    # -- read / write -------------------------------------------------------
    def write(self, payload: bytes) -> SlotRef:
        """Write ``payload`` to the next slot (overwriting the oldest) and return its ref."""
        if len(payload) > self._slot_size:
            raise ValueError(
                f"payload of {len(payload)} bytes exceeds slot_size {self._slot_size}"
            )
        write_idx = self._read_write_idx()
        slot = write_idx % self._n_slots
        gen = self._read_slot_header(slot)[0] + 1
        _SLOT.pack_into(self._buf, self._slot_off(slot), gen, len(payload))
        start = self._data_off + slot * self._slot_size
        self._buf[start : start + len(payload)] = payload
        self._set_write_idx(write_idx + 1)
        return SlotRef(slot=slot, gen=gen, length=len(payload))

    def read_slot(self, slot: int, gen: int, length: int) -> bytes | None:
        """Copy a slot's payload, or ``None`` if its generation no longer matches ``gen``."""
        if self._read_slot_header(slot)[0] != gen:
            return None  # already overwritten before we read
        start = self._data_off + slot * self._slot_size
        payload = bytes(self._buf[start : start + length])
        if self._read_slot_header(slot)[0] != gen:
            return None  # overwritten during the copy
        return payload

    # -- lifecycle ----------------------------------------------------------
    def close(self) -> None:
        """Detach this handle from the segment."""
        self._buf = None
        self._shm.close()

    def unlink(self) -> None:
        """Free the segment (owner only)."""
        if self._owner:
            self._shm.unlink()


def sweep_stale_segments(prefix: str = _SEGMENT_PREFIX) -> list[str]:
    """Unlink leftover ``mmco-*`` shared-memory segments; return the names removed.

    POSIX-only: segments live in ``/dev/shm``. A no-op on platforms without it.
    """
    removed: list[str] = []
    shm_dir = "/dev/shm"
    if not os.path.isdir(shm_dir):
        return removed
    for fname in os.listdir(shm_dir):
        if not fname.startswith(prefix):
            continue
        try:
            seg = shared_memory.SharedMemory(name=fname)
            seg.close()
            seg.unlink()
            removed.append(fname)
        except FileNotFoundError:
            pass
    return removed

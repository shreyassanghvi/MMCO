import sys

import pytest

from mmco.bus.ring import RingBuffer, sweep_stale_segments


def test_write_then_read_slot_returns_same_bytes():
    ring = RingBuffer.create(n_slots=4, slot_size=16)
    try:
        ref = ring.write(b"hello")
        assert ring.read_slot(ref.slot, ref.gen, ref.length) == b"hello"
    finally:
        ring.close()
        ring.unlink()


def test_wrap_around_each_just_written_slot_is_readable():
    ring = RingBuffer.create(n_slots=4, slot_size=16)
    try:
        for i in range(10):  # more than n_slots -> wraps
            payload = f"p{i}".encode()
            ref = ring.write(payload)
            assert ring.read_slot(ref.slot, ref.gen, ref.length) == payload
    finally:
        ring.close()
        ring.unlink()


def test_slot_generation_increases_on_reuse():
    ring = RingBuffer.create(n_slots=2, slot_size=16)
    try:
        first = ring.write(b"a")  # slot 0, gen 1
        ring.write(b"b")  # slot 1, gen 1
        reuse = ring.write(b"c")  # slot 0 again
        assert reuse.slot == first.slot
        assert reuse.gen > first.gen
    finally:
        ring.close()
        ring.unlink()


def test_read_with_stale_gen_returns_none():
    ring = RingBuffer.create(n_slots=2, slot_size=16)
    try:
        first = ring.write(b"a")  # slot 0, gen 1
        ring.write(b"b")  # slot 1
        ring.write(b"c")  # slot 0 overwritten, gen 2
        # reading slot 0 with the stale gen from `first` must be rejected
        assert ring.read_slot(first.slot, first.gen, first.length) is None
    finally:
        ring.close()
        ring.unlink()


def test_oversize_payload_raises():
    ring = RingBuffer.create(n_slots=2, slot_size=4)
    try:
        with pytest.raises(ValueError):
            ring.write(b"too-long-payload")
    finally:
        ring.close()
        ring.unlink()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX /dev/shm semantics")
def test_sweep_stale_segments_removes_leftovers():
    leftover = RingBuffer.create(n_slots=1, slot_size=4)
    name = leftover.name
    leftover.close()  # deliberately do NOT unlink -> simulate a leaked segment
    removed = sweep_stale_segments()
    assert name in removed

from mmco.bus.metaqueue import MetaQueue
from mmco.core.events import EventMeta


def _meta(seq: int) -> EventMeta:
    return EventMeta(
        sensor_id="cam0",
        seq=seq,
        t_acquire_ns=seq * 10,
        slot=seq % 4,
        length=128,
        gen=1,
    )


def test_put_then_get_round_trips_including_gen():
    q = MetaQueue()
    try:
        meta = _meta(3)
        assert q.put(meta) is True
        got = q.get(timeout=1.0)
        assert got == meta
        assert got.gen == 1
    finally:
        q.close()


def test_fifo_order_is_preserved():
    q = MetaQueue()
    try:
        for i in range(5):
            assert q.put(_meta(i)) is True
        seqs = [q.get(timeout=1.0).seq for _ in range(5)]
        assert seqs == [0, 1, 2, 3, 4]
    finally:
        q.close()


def test_get_on_empty_returns_none():
    q = MetaQueue()
    try:
        assert q.get(timeout=0.05) is None
    finally:
        q.close()


def test_put_on_full_returns_false():
    q = MetaQueue(maxsize=1)
    try:
        assert q.put(_meta(0)) is True
        assert q.put(_meta(1)) is False
    finally:
        q.close()

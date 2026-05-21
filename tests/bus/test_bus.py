from mmco.bus.bus import BusConsumer, BusProducer
from mmco.bus.metaqueue import MetaQueue
from mmco.bus.ring import RingBuffer
from mmco.core.errors import ErrorCode


def test_publish_then_poll_delivers_meta_and_payload_intact():
    ring = RingBuffer.create(n_slots=4, slot_size=32)
    mq = MetaQueue()
    try:
        producer = BusProducer(ring, mq)
        consumer = BusConsumer(ring, mq)
        assert (
            producer.publish(
                sensor_id="cam0", seq=1, t_acquire_ns=1_000, payload=b"frame"
            )
            is None
        )
        result = consumer.poll(timeout=1.0)
        assert result is not None
        meta, payload = result
        assert payload == b"frame"
        assert meta.sensor_id == "cam0"
        assert meta.seq == 1
        assert meta.t_acquire_ns == 1_000
    finally:
        mq.close()
        ring.close()
        ring.unlink()


def test_publish_on_full_queue_reports_backpressure():
    ring = RingBuffer.create(n_slots=4, slot_size=32)
    mq = MetaQueue(maxsize=1)
    try:
        producer = BusProducer(ring, mq)
        assert producer.publish(sensor_id="cam0", seq=1, t_acquire_ns=1, payload=b"a") is None
        code = producer.publish(sensor_id="cam0", seq=2, t_acquire_ns=2, payload=b"b")
        assert code is ErrorCode.SHM_BUFFER_FULL
        assert producer.dropped == 1
    finally:
        mq.close()
        ring.close()
        ring.unlink()


def test_poll_rejects_lapped_slot_and_counts_drop():
    ring = RingBuffer.create(n_slots=2, slot_size=8)
    mq = MetaQueue()
    try:
        producer = BusProducer(ring, mq)
        consumer = BusConsumer(ring, mq)
        producer.publish(sensor_id="imu0", seq=1, t_acquire_ns=1, payload=b"a")  # slot0 gen1
        producer.publish(sensor_id="imu0", seq=2, t_acquire_ns=2, payload=b"b")  # slot1 gen1
        producer.publish(sensor_id="imu0", seq=3, t_acquire_ns=3, payload=b"c")  # slot0 gen2

        # first meta points at slot0/gen1, which has been overwritten -> drop, no torn bytes
        assert consumer.poll(timeout=1.0) is None
        assert consumer.dropped == 1
        # the remaining records still deliver intact
        _, b_payload = consumer.poll(timeout=1.0)
        assert b_payload == b"b"
        _, c_payload = consumer.poll(timeout=1.0)
        assert c_payload == b"c"
    finally:
        mq.close()
        ring.close()
        ring.unlink()

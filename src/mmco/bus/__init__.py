"""The MMCO event bus: a shared-memory payload ring plus a metadata queue.

Payloads (frames, audio buffers, IMU rows) move through a :mod:`~mmco.bus.ring` shared-memory ring so
big buffers are never pickled; small fixed-size metadata records travel on a
:mod:`~mmco.bus.metaqueue`. :mod:`~mmco.bus.bus` composes the two into producer/consumer handles.
"""

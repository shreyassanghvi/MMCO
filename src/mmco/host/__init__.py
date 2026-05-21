"""The driver-host layer: the process wrapper around a single sensor driver.

The core spawns one :mod:`~mmco.host.driver_host` child per sensor and wires it with the control and
log channels from :mod:`~mmco.host.control`: a stop signal flows core → host, and the host's
``LogEvent``s flow host → core.
"""

"""Typed exceptions -- the library never prints-and-returns-None (spec bugs #3, #8)."""

from __future__ import annotations


class HM310TError(Exception):
    """Base class for everything this library raises."""


class PowerSupplyCommunicationError(HM310TError):
    """Connect failure, read/write failure, or a Modbus error response."""


class OutOfRangeError(HM310TError, ValueError):
    """A setpoint outside its allowed range. Nothing is written to the device."""


class IncompatibleDeviceError(HM310TError):
    """The connected device reports capabilities this library was not built for."""

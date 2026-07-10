"""Control a Hanmatek HM310T power supply over Modbus RTU."""

from importlib.metadata import version as _version

from .client import Measurement, PowerSupply, ProtectionStatus
from .exceptions import (
    HM310TError,
    IncompatibleDeviceError,
    OutOfRangeError,
    PowerSupplyCommunicationError,
)

__version__ = _version("hm310t")

__all__ = [
    "PowerSupply",
    "Measurement",
    "ProtectionStatus",
    "HM310TError",
    "PowerSupplyCommunicationError",
    "OutOfRangeError",
    "IncompatibleDeviceError",
    "__version__",
]

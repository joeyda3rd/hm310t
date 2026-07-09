"""Control a Hanmatek HM310T power supply over Modbus RTU."""

from .client import PowerSupply
from .exceptions import (
    HM310TError,
    IncompatibleDeviceError,
    OutOfRangeError,
    PowerSupplyCommunicationError,
)

__version__ = "0.1.0"

__all__ = [
    "PowerSupply",
    "HM310TError",
    "PowerSupplyCommunicationError",
    "OutOfRangeError",
    "IncompatibleDeviceError",
    "__version__",
]

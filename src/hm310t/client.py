"""PowerSupply domain class: the public API of hm310t."""

from __future__ import annotations

from . import registers
from .exceptions import IncompatibleDeviceError
from .transport import Transport

# Register 0x0003 encodes the rated spec: 3010 == 30 V / 10 A (the HM310T).
# Confirmed against the real unit in Task 0. A same-family sibling (e.g. an HM305,
# 30 V / 5 A -> 3005) reports identical decimals and must be rejected here.
EXPECTED_SPECIFICATION = 3010


class PowerSupply:
    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        slave: int = 1,
        voltage_limit: float = 30.0,
        current_limit: float = 10.0,
    ) -> None:
        self.voltage_limit = voltage_limit
        self.current_limit = current_limit
        self._transport = Transport(port, baudrate=baudrate, slave=slave)
        try:
            self._transport.connect()
            self._check_decimal_capacity()
            self._check_specification()
        except BaseException:
            # Spec bug #1: never leak the serial handle if connect or post-connect
            # verification fails partway (close() is safe on a never-opened port).
            self._transport.close()
            raise

    def _check_decimal_capacity(self) -> None:
        """Register 0x0005 reports the device's real display precision (e.g. 0x0233 =
        voltage 2dp, current 3dp, power 3dp). A firmware variant with different
        precision fails loudly here instead of silently producing wrong values."""
        raw = self._transport.read_register(registers.DECIMAL_CAPACITY)
        reported = ((raw >> 8) & 0xF, (raw >> 4) & 0xF, raw & 0xF)
        expected = (
            registers.VOLTAGE.decimals,
            registers.CURRENT.decimals,
            registers.POWER_DISPLAY.decimals,
        )
        if reported != expected:
            raise IncompatibleDeviceError(
                f"Device reports decimal capacity 0x{raw:04X} (V/A/W = {reported}); "
                f"this library expects {expected}"
            )

    def _check_specification(self) -> None:
        """Register 0x0003 encodes the device's rated spec (3010 = 30 V / 10 A).

        The 0x0005 decimal check can't distinguish a same-family sibling: an HM305
        (30 V / 5 A) reports the same 0x0233 decimals as an HM310T yet has a lower
        current rating than this library's 10 A default assumes. This catches it.
        The expected value is confirmed against the real unit in Task 0.
        """
        spec = self._transport.read_register(registers.SPECIFICATION)
        if spec != EXPECTED_SPECIFICATION:
            raise IncompatibleDeviceError(
                f"Device specification register (0x0003) reads {spec}, expected "
                f"{EXPECTED_SPECIFICATION} (HM310T, 30 V / 10 A) -- this may be a "
                "different model in the same family; this library targets the HM310T."
            )

    def close(self) -> None:
        """Close the serial connection.

        Does NOT disable the output -- the supply keeps sourcing at its setpoints.
        Call ``output_enabled = False`` first if you want the output off (see the
        README "Known limitations"). Leaving the output running on purpose is a
        legitimate bench workflow, so closing does not force it off.
        """
        self._transport.close()

    def __enter__(self) -> PowerSupply:
        return self

    def __exit__(self, *exc: object) -> None:
        # Closes the connection only; deliberately does NOT disable the output.
        self.close()

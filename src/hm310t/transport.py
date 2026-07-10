"""Raw Modbus RTU I/O for the HM310T. Knows nothing about volts or amps.

Internal module: the public API is hm310t.PowerSupply. This seam exists so
client logic is unit-testable without hardware (tests/test_client.py).
"""

from __future__ import annotations

from typing import Any

from pymodbus.client import ModbusSerialClient

from .exceptions import PowerSupplyCommunicationError


class Transport:
    def __init__(
        self, port: str, baudrate: int = 9600, slave: int = 1, timeout: float = 1.0
    ) -> None:
        self.slave = slave
        # pymodbus 3.2.2 ships incomplete type info; treat the client as the untyped
        # boundary (what this seam is for) so strict mypy stays clean above it.
        self._client: Any = ModbusSerialClient(port=port, baudrate=baudrate, timeout=timeout)

    def connect(self) -> None:
        try:
            connected = self._client.connect()
        except Exception as exc:  # pyserial/pymodbus may raise instead of returning False
            raise PowerSupplyCommunicationError(f"Failed to open serial connection: {exc}") from exc
        if not connected:
            raise PowerSupplyCommunicationError(
                "Failed to open serial connection to the power supply"
            )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception as exc:
            raise PowerSupplyCommunicationError(f"Failed to close serial connection: {exc}") from exc

    def read_registers(self, address: int, count: int) -> list[int]:
        try:
            response = self._client.read_holding_registers(address, count=count, slave=self.slave)
        except Exception as exc:  # pymodbus/pyserial may raise; catch broadly (bug #8)
            raise PowerSupplyCommunicationError(
                f"Read of register 0x{address:04X} failed: {exc}"
            ) from exc
        if response is None or response.isError():
            raise PowerSupplyCommunicationError(
                f"Read of register 0x{address:04X} failed: {response}"
            )
        registers: list[int] = list(response.registers)
        # A short (but non-error) response must not become an IndexError two layers
        # up: keep the "all failures are typed" contract at the transport boundary.
        if len(registers) != count:
            raise PowerSupplyCommunicationError(
                f"Read of register 0x{address:04X} returned {len(registers)} "
                f"register(s), expected {count}"
            )
        return registers

    def read_register(self, address: int) -> int:
        return self.read_registers(address, 1)[0]

    def write_register(self, address: int, value: int) -> None:
        try:
            response = self._client.write_register(address, value, slave=self.slave)
        except Exception as exc:
            raise PowerSupplyCommunicationError(
                f"Write to register 0x{address:04X} failed: {exc}"
            ) from exc
        if response is None or response.isError():
            raise PowerSupplyCommunicationError(
                f"Write to register 0x{address:04X} failed: {response}"
            )

    def write_registers(self, address: int, values: list[int]) -> None:
        """FC16 multi-register write -- verified working on real hardware despite
        the OEM doc's claim that only FC03/FC06 are supported. A unit that
        rejects it gets a loud error, never a silent two-FC06 fallback.
        """
        try:
            response = self._client.write_registers(address, values, slave=self.slave)
        except Exception as exc:
            raise PowerSupplyCommunicationError(
                f"Multi-register write (FC16) at 0x{address:04X} failed: {exc}. "
                "The OEM doc claims only FC03/FC06 support; this unit may actually enforce that."
            ) from exc
        if response is None or response.isError():
            raise PowerSupplyCommunicationError(
                f"Multi-register write (FC16) at 0x{address:04X} failed: {response}. "
                "The OEM doc claims only FC03/FC06 support; this unit may actually enforce that."
            )

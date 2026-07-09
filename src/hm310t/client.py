"""PowerSupply domain class: the public API of hm310t."""

from __future__ import annotations

from dataclasses import dataclass

from . import registers
from .exceptions import IncompatibleDeviceError, OutOfRangeError
from .registers import ScaledRegister
from .transport import Transport

# Register 0x0003 encodes the rated spec: 3010 == 30 V / 10 A (the HM310T).
# Confirmed against the real unit in Task 0. A same-family sibling (e.g. an HM305,
# 30 V / 5 A -> 3005) reports identical decimals and must be rejected here.
EXPECTED_SPECIFICATION = 3010


@dataclass(frozen=True)
class Measurement:
    """One atomic snapshot of the live output (display registers 0x0010-0x0013)."""

    voltage: float
    current: float
    power: float


@dataclass(frozen=True)
class ProtectionStatus:
    is_ovp: bool
    is_ocp: bool
    is_opp: bool
    is_otp: bool
    is_scp: bool

    @property
    def tripped(self) -> bool:
        return any((self.is_ovp, self.is_ocp, self.is_opp, self.is_otp, self.is_scp))


# Protection trip points are device hardware limits, deliberately independent of
# the constructor's voltage_limit/current_limit software ceilings (spec decision).
_OVP_RANGE = (0.0, 30.0)
_OCP_RANGE = (0.0, 10.0)
_OPP_RANGE = (0.0, 300.0)


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

    def _read_scaled(self, register: ScaledRegister) -> float:
        if register.words == 1:
            raw = self._transport.read_register(register.address)
        else:
            high, low = self._transport.read_registers(register.address, 2)
            raw = (high << 16) | low
        return register.from_raw(raw)

    def _write_scaled(
        self, register: ScaledRegister, value: float, low: float, high: float, name: str
    ) -> None:
        if not low <= value <= high:
            raise OutOfRangeError(f"{name} must be between {low} and {high}, got {value}")
        raw = register.to_raw(value)
        if register.words == 1:
            self._transport.write_register(register.address, raw)
        else:
            # One atomic FC16 write -- no torn-write window (spec, "Hardware behavior").
            self._transport.write_registers(register.address, [(raw >> 16) & 0xFFFF, raw & 0xFFFF])

    @property
    def voltage(self) -> float:
        """The voltage *setpoint* (0x0030). Live output is read_measurement().voltage."""
        return self._read_scaled(registers.VOLTAGE)

    @voltage.setter
    def voltage(self, value: float) -> None:
        self._write_scaled(registers.VOLTAGE, value, 0.0, self.voltage_limit, "voltage")

    @property
    def current(self) -> float:
        """The current *setpoint* (0x0031). Live output is read_measurement().current."""
        return self._read_scaled(registers.CURRENT)

    @current.setter
    def current(self, value: float) -> None:
        self._write_scaled(registers.CURRENT, value, 0.0, self.current_limit, "current")

    @property
    def ovp(self) -> float:
        return self._read_scaled(registers.OVP)

    @ovp.setter
    def ovp(self, value: float) -> None:
        self._write_scaled(registers.OVP, value, _OVP_RANGE[0], _OVP_RANGE[1], "ovp")

    @property
    def ocp(self) -> float:
        return self._read_scaled(registers.OCP)

    @ocp.setter
    def ocp(self, value: float) -> None:
        self._write_scaled(registers.OCP, value, _OCP_RANGE[0], _OCP_RANGE[1], "ocp")

    @property
    def opp(self) -> float:
        return self._read_scaled(registers.OPP)

    @opp.setter
    def opp(self, value: float) -> None:
        self._write_scaled(registers.OPP, value, _OPP_RANGE[0], _OPP_RANGE[1], "opp")

    @property
    def comm_address(self) -> int:
        return self._transport.read_register(registers.COMM_ADDRESS)

    @comm_address.setter
    def comm_address(self, value: int) -> None:
        if not 1 <= value <= 250:
            raise OutOfRangeError(f"comm_address must be between 1 and 250, got {value}")
        # If this write raises, the device may or may not have switched address;
        # state is indeterminate -- reconnect and probe both before trusting either.
        self._transport.write_register(registers.COMM_ADDRESS, value)
        self._transport.slave = value  # keep talking to the device at its new address

    @property
    def output_enabled(self) -> bool:
        return bool(self._transport.read_register(registers.OUTPUT))

    @output_enabled.setter
    def output_enabled(self, value: bool) -> None:
        self._transport.write_register(registers.OUTPUT, int(bool(value)))

    def read_measurement(self) -> Measurement:
        """Read voltage/current/power display in ONE Modbus transaction (no torn reads)."""
        regs = self._transport.read_registers(registers.VOLTAGE_DISPLAY.address, 4)
        return Measurement(
            voltage=registers.VOLTAGE_DISPLAY.from_raw(regs[0]),
            current=registers.CURRENT_DISPLAY.from_raw(regs[1]),
            power=registers.POWER_DISPLAY.from_raw((regs[2] << 16) | regs[3]),
        )

    def read_protection_status(self) -> ProtectionStatus:
        # Bit order per the OEM doc's _ST union (Note 1), LSB-first, matching the
        # original pyHM310T decoding. Per-bit hardware verification would require
        # deliberately tripping each protection -- out of scope for the test suite.
        raw = self._transport.read_register(registers.PROTECT_STATUS)
        return ProtectionStatus(
            is_ovp=bool(raw & 0x01),
            is_ocp=bool(raw & 0x02),
            is_opp=bool(raw & 0x04),
            is_otp=bool(raw & 0x08),
            is_scp=bool(raw & 0x10),
        )

    def read_raw_register(self, address: int) -> int:
        """Escape hatch: read any holding register, bypassing the typed register model."""
        return self._transport.read_register(address)

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

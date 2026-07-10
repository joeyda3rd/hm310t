"""Register map for the HM310T, from OEM-docs/Modbus.pdf.

Addresses and scaling are exercised against the real device by tests/test_contract.py;
the FC16 multi-register write path is explicitly hardware-verified (see the spec).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScaledRegister:
    """A holding register storing a fixed-point value.

    words=2 means a 32-bit value spanning [address, address + 1], high word first.
    """

    address: int
    decimals: int  # register_value = round(real_value * 10**decimals)
    words: int = 1

    def to_raw(self, value: float) -> int:
        scale: int = 10**self.decimals
        return round(value * scale)

    def from_raw(self, raw: int) -> float:
        scale: int = 10**self.decimals
        return raw / scale


# Unscaled registers
OUTPUT = 0x0001  # bool: output on/off
PROTECT_STATUS = 0x0002  # bit field, see client.ProtectionStatus
SPECIFICATION = 0x0003  # rated spec/type: 3010 = 30 V / 10 A (connect-time identity check)
DECIMAL_CAPACITY = 0x0005  # read-only nibbles: 0x0233 = V 2dp, A 3dp, W 3dp
COMM_ADDRESS = 0x9999  # slave address, 1-250
# 0x0004 "Tail classification": documented but unmapped -- value semantics are not in
# the OEM doc; reach it via PowerSupply.read_raw_register(0x0004) if ever needed.

# Live measurement (read-only), contiguous 0x0010-0x0013
VOLTAGE_DISPLAY = ScaledRegister(0x0010, decimals=2)
CURRENT_DISPLAY = ScaledRegister(0x0011, decimals=3)
POWER_DISPLAY = ScaledRegister(0x0012, decimals=3, words=2)

# Setpoints
VOLTAGE = ScaledRegister(0x0030, decimals=2)
CURRENT = ScaledRegister(0x0031, decimals=3)

# Protection trip points
OVP = ScaledRegister(0x0020, decimals=2)
OCP = ScaledRegister(
    0x0021, decimals=3
)  # 3dp like current (amperage display), not 2 like voltage/OVP
OPP = ScaledRegister(0x0022, decimals=2, words=2)

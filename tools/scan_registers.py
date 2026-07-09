"""Read-only register scanner for a real HM310T (ported from the old modbus_read.py).

Standalone: raw pymodbus, no dependency on the hm310t package. It only READS
holding registers, so it never changes device state or energizes the output.
Handy for eyeballing the live register map or debugging a suspect unit.

    python tools/scan_registers.py            # uses /dev/ttyUSB0
"""

from __future__ import annotations

import sys
import time

from pymodbus.client import ModbusSerialClient

PORT = "/dev/ttyUSB0"
SLAVE = 1

# Address -> human label, in the OEM doc's order.
REGISTERS = {
    0x0001: "Output on/off",
    0x0002: "Protect status",
    0x0003: "Specification",
    0x0004: "Tail classification",
    0x0005: "Decimal capacity",
    0x0010: "V display",
    0x0011: "I display",
    0x0012: "P display high",
    0x0013: "P display low",
    0x0020: "OVP",
    0x0021: "OCP",
    0x0022: "OPP high",
    0x0023: "OPP low",
    0x0030: "Set V",
    0x0031: "Set I",
    0x9999: "Comm address",
}


def main() -> None:
    client = ModbusSerialClient(PORT, baudrate=9600, timeout=1)
    if not client.connect():
        sys.exit(f"Could not connect on {PORT}")
    try:
        for address, label in REGISTERS.items():
            response = client.read_holding_registers(address, count=1, slave=SLAVE)
            if response is None or response.isError():
                print(f"0x{address:04X}  {label:20} = ERROR ({response})")
            else:
                print(f"0x{address:04X}  {label:20} = {response.registers}")
            time.sleep(0.035)  # the unit needs a beat between transactions
    finally:
        client.close()


if __name__ == "__main__":
    main()

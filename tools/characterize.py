"""One-shot characterization of the real HM310T.

Confirms the register map, scaling, and byte order that registers.py encodes --
against the physical unit, BEFORE the library is built on them. Output stays OFF
throughout. Standalone: raw pymodbus, no dependency on the hm310t package.

Run once and commit the printed output as evidence:
    python tools/characterize.py | tee docs/hardware-characterization-2026-07-09.md
"""

from __future__ import annotations

import sys

from pymodbus.client import ModbusSerialClient

PORT = "/dev/ttyUSB0"
SLAVE = 1

DOCUMENTED = {
    0x0001: "Output on/off",
    0x0002: "Protect status",
    0x0003: "Specification/type",
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


def read(client, address, count=1):
    response = client.read_holding_registers(address, count=count, slave=SLAVE)
    if response is None or response.isError():
        return None
    return response.registers


def write(client, address, values):
    if isinstance(values, int):
        response = client.write_register(address, values, slave=SLAVE)
    else:
        response = client.write_registers(address, values, slave=SLAVE)
    return response is not None and not response.isError()


def valid_snapshot(values, count):
    return values is not None and len(values) == count


def main():
    client = ModbusSerialClient(port=PORT, baudrate=9600, timeout=1)
    if not client.connect():
        sys.exit(f"Could not connect on {PORT}")

    setv0 = None
    opp0 = None
    cleanup_errors = []
    try:
        output = read(client, 0x0001)
        print(f"# Output at start: {output}  (must be [0]; abort if not)")
        if output != [0]:  # explicit check, NOT assert -- must survive `python -O`
            sys.exit("OUTPUT IS ON -- aborting; disable it first")

        setv0 = read(client, 0x0030)
        opp0 = read(client, 0x0022, 2)
        if not valid_snapshot(setv0, 1) or not valid_snapshot(opp0, 2):
            raise RuntimeError("Could not snapshot voltage and OPP; refusing to write settings")

        print("\n## Documented register dump")
        for address, name in DOCUMENTED.items():
            print(f"0x{address:04X}  {name:20} = {read(client, address)}")

        print("\n## Identity")
        print(f"0x0003 specification = {read(client, 0x0003)}  (expect [3010] = 30 V / 10 A)")
        print(f"0x0004 tail class    = {read(client, 0x0004)}  (record; semantics undocumented)")
        print(f"0x0005 decimals      = {read(client, 0x0005)}  (expect [{0x0233}] = 0x0233)")

        print("\n## Scaling (write setpoint, read raw; output stays off)")
        if not write(client, 0x0030, 200):
            raise RuntimeError("Could not write voltage setpoint")
        print(f"wrote Set V 2.00 -> raw 0x0030 = {read(client, 0x0030)}  (expect [200])")

        print("\n## Byte order (asymmetric OPP, read both words)")
        if not write(client, 0x0022, [0, 20000]):
            raise RuntimeError("Could not write OPP setpoint")
        print(f"wrote OPP 200.0 -> 0x0022 = {read(client, 0x0022)} (expect [0])")
        print(f"                  0x0023 = {read(client, 0x0023)} (expect [20000])")

        print("\n## FC16 effective? (write a different value, read back)")
        if not write(client, 0x0022, [0, 10000]):
            raise RuntimeError("Could not write OPP through FC16")
        print(f"wrote OPP 100.0 via FC16 -> read back {read(client, 0x0022, 2)}")
        print("  Effective if the read shows [0, 10000] (restored below).")

        print("\n## Error semantics (read an undocumented address)")
        response = client.read_holding_registers(0x00FF, count=1, slave=SLAVE)
        flagged = None if response is None else response.isError()
        print(f"0x00FF -> isError={flagged}  (flags bad reads, or returns junk?)")

        print("\n## Read-only sweep 0x0000-0x0040 (flag undocumented responders)")
        for address in range(0x0000, 0x0041):
            regs = read(client, address)
            if regs is not None and address not in DOCUMENTED:
                print(f"  UNDOCUMENTED 0x{address:04X} = {regs}  <- check against the doc")
    finally:
        # Force output off first. Never restore a setting to a possibly live output.
        output_is_off = False
        try:
            output_is_off = write(client, 0x0001, 0)
            if not output_is_off:
                cleanup_errors.append("could not turn output off")
        except Exception as exc:
            cleanup_errors.append(f"could not turn output off: {exc!r}")

        if output_is_off:
            if valid_snapshot(setv0, 1):
                try:
                    if not write(client, 0x0030, setv0[0]):
                        cleanup_errors.append("could not restore voltage")
                except Exception as exc:
                    cleanup_errors.append(f"could not restore voltage: {exc!r}")
            if valid_snapshot(opp0, 2):
                try:
                    if not write(client, 0x0022, opp0):
                        cleanup_errors.append("could not restore OPP")
                except Exception as exc:
                    cleanup_errors.append(f"could not restore OPP: {exc!r}")

        try:
            client.close()
        except Exception as exc:
            cleanup_errors.append(f"could not close connection: {exc!r}")

        if cleanup_errors:
            raise RuntimeError(f"Characterization cleanup failed: {cleanup_errors}")


if __name__ == "__main__":
    main()

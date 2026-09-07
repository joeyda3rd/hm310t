"""Write-path smoke test against a real HM310T.

Validates the installed ``hm310t`` package end-to-end: for each setpoint and
protection register it writes a test value, reads it back through the public API,
and verifies the value round-trips on the real device. Prints a PASS/FAIL line per
check and a summary; exits non-zero if any check fails.

The OUTPUT IS NEVER ENABLED -- this exercises writes only, with the output off the
whole time. It snapshots the device's current setpoints up front and restores them
in a ``finally``, leaving the device as it was found. It refuses to run if the
output is already on (writing setpoints to a live output would change what it
regulates to). Standalone and opt-in -- not part of the pytest suite.

    python tools/smoke_write.py                     # uses /dev/ttyUSB0
    PSU_TEST_PORT=/dev/ttyUSB1 python tools/smoke_write.py
"""

from __future__ import annotations

import math
import os
import sys
import time

from hm310t import PowerSupply

PORT = os.environ.get("PSU_TEST_PORT", "/dev/ttyUSB0")

# The HM310T drops transactions if hammered without a beat between them -- most
# visibly a read issued immediately after an FC16 (multi-register) write. The
# library does not pace for you; a tight loop like this must. (Same reason
# tools/scan_registers.py and characterize.py sleep between transactions.)
PACING_S = 0.05

# (attribute, test value, decimals). Test values are within the 30 V / 10 A / 300 W
# rating and already at the register's precision, so a correct round-trip reads back
# to within half a least-count.
CHECKS = [
    ("voltage", 3.33, 2),
    ("current", 0.250, 3),
    ("ovp", 12.50, 2),
    ("ocp", 1.50, 3),
    ("opp", 120.0, 2),
]

SNAPSHOT_ATTRS = [name for name, _, _ in CHECKS]


def main() -> None:
    try:
        psu = PowerSupply(port=PORT)
    except Exception as exc:
        sys.exit(f"Could not open a HM310T on {PORT}: {exc}")

    baseline = None
    results: list[bool] = []
    restore_errors: list[str] = []
    try:
        if psu.output_enabled:
            sys.exit("OUTPUT IS ON -- aborting; disable it before running the write smoke.")

        baseline = {name: getattr(psu, name) for name in SNAPSHOT_ATTRS}
        print(f"Connected on {PORT}. Output off. Baseline captured; will restore on exit.\n")

        for name, value, decimals in CHECKS:
            try:
                setattr(psu, name, value)
                time.sleep(PACING_S)  # let the write settle before reading it back
                readback = getattr(psu, name)
                ok = math.isclose(readback, value, abs_tol=0.5 * 10 ** (-decimals))
                print(f"  [{'PASS' if ok else 'FAIL'}] {name:8} wrote {value:<7} read {readback}")
            except Exception as exc:  # a smoke run reports the failure, keeps going
                ok = False
                print(f"  [FAIL] {name:8} wrote {value:<7} raised {exc!r}")
            results.append(ok)
    finally:
        if baseline is not None:
            for name in SNAPSHOT_ATTRS:
                try:
                    setattr(psu, name, baseline[name])
                    time.sleep(PACING_S)  # pace the restore writes too (FC16 opp included)
                except Exception as exc:
                    restore_errors.append(f"{name}: {exc!r}")
        try:
            psu.close()
        except Exception as exc:
            restore_errors.append(f"close: {exc!r}")
        if restore_errors:
            print(f"\nFAIL: could not fully restore baseline: {restore_errors}", file=sys.stderr)

    passed = sum(results)
    print(f"\n{passed}/{len(results)} write round-trips verified.")
    if passed != len(results) or restore_errors:
        sys.exit(1)
    print("SMOKE PASS")


if __name__ == "__main__":
    main()

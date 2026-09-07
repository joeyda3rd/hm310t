"""Basic usage of the hm310t library against a real HM310T.

CAUTION: This script ENERGIZES the output. The HM310T can source up to 10 A /
300 W -- a real hazard. Run it only with nothing (or a known-safe load) wired to
the terminals. It sets conservative protection trip points BEFORE enabling the
output and GUARANTEES the output is disabled again in a ``finally`` block.

    python examples/basic_usage.py            # uses /dev/ttyUSB0
"""

from __future__ import annotations

from hm310t import PowerSupply


def main() -> None:
    # port, baudrate=9600, slave=1, voltage_limit=30.0, current_limit=10.0
    with PowerSupply(port="/dev/ttyUSB0") as psu:
        # Connecting preserves output state, so explicitly turn it off before
        # changing any setting. A pre-existing live output must not be reconfigured.
        psu.output_enabled = False

        # Set protection trip points first, while the output is off.
        psu.ovp = 6.0
        psu.ocp = 0.1
        psu.opp = 5.0

        # Setpoints (these are the limits the output will regulate to).
        psu.voltage = 5.0
        psu.current = 0.05
        print(f"Setpoints -> voltage: {psu.voltage} V, current: {psu.current} A")
        print(f"Protection -> OVP: {psu.ovp} V, OCP: {psu.ocp} A, OPP: {psu.opp} W")

        try:
            psu.output_enabled = True
            print(f"Output enabled: {psu.output_enabled}")

            # Live output measurement (one atomic read; needs a load to read non-zero).
            m = psu.read_measurement()
            print(f"Measured -> {m.voltage} V, {m.current} A, {m.power} W")

            status = psu.read_protection_status()
            print(f"Protection tripped: {status.tripped}  ({status})")
        finally:
            # Always leave the output off, even if the block above raised.
            psu.output_enabled = False
            print(f"Output enabled: {psu.output_enabled}")

    # NB: leaving the `with` block closes the serial connection but does NOT by
    # itself disable the output -- that is why we disable it explicitly above.


if __name__ == "__main__":
    main()

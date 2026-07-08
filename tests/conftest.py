import os

import pytest

from pyHM310T import PowerSupply

PSU_PORT = os.environ.get("PSU_TEST_PORT", "/dev/ttyUSB0")


@pytest.fixture
def power_supply():
    try:
        psu = PowerSupply(port=PSU_PORT)
    except Exception as exc:
        pytest.skip(f"No power supply reachable at {PSU_PORT}: {exc}")

    baseline = {
        "voltage": psu.get_voltage(),
        "current": psu.get_current(),
        "ovp": psu.get_ovp(),
        "ocp": psu.get_ocp(),
        "opp": psu.get_opp(),
        "output_enabled": psu.is_output_enabled(),
    }

    # Force output off for the duration of the test, regardless of the
    # baseline we found it in -- tests that probe setpoint boundaries rely
    # on output actually being off, not just on whatever state we inherited.
    if baseline["output_enabled"]:
        psu.disable_output()

    try:
        yield psu
    finally:
        # Restore each value independently so one failing call (comms
        # hiccup, USB re-enumeration) can't skip the rest -- output restore
        # runs last and unconditionally, since it's the safety-critical one.
        restore_steps = [
            ("voltage", lambda: psu.set_voltage(baseline["voltage"])),
            ("current", lambda: psu.set_current(baseline["current"])),
            ("ovp", lambda: psu.set_ovp(baseline["ovp"])),
            ("ocp", lambda: psu.set_ocp(baseline["ocp"])),
            ("opp", lambda: psu.set_opp(baseline["opp"])),
        ]
        errors = []
        for name, restore in restore_steps:
            try:
                restore()
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        try:
            psu.enable_output(baseline["output_enabled"])
        except Exception as exc:
            errors.append(f"output_enabled: {exc}")
        psu.close()
        if errors:
            raise AssertionError(
                "Failed to fully restore power supply state: " + "; ".join(errors)
            )

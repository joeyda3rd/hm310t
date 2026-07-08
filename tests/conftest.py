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
        return

    baseline = {
        "voltage": psu.get_voltage(),
        "current": psu.get_current(),
        "ovp": psu.get_ovp(),
        "ocp": psu.get_ocp(),
        "opp": psu.get_opp(),
        "output_enabled": psu.is_output_enabled(),
    }

    try:
        yield psu
    finally:
        psu.set_voltage(baseline["voltage"])
        psu.set_current(baseline["current"])
        psu.set_ovp(baseline["ovp"])
        psu.set_ocp(baseline["ocp"])
        psu.set_opp(baseline["opp"])
        if psu.is_output_enabled() != baseline["output_enabled"]:
            psu.enable_output(baseline["output_enabled"])

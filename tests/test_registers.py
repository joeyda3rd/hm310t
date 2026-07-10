"""Hardware-free tests for the register map and fixed-point scaling."""

from __future__ import annotations

import pytest

from hm310t.exceptions import HM310TError, OutOfRangeError
from hm310t.registers import CURRENT, OCP, OPP, POWER_DISPLAY, VOLTAGE


def test_to_raw_rounds_instead_of_truncating():
    # Spec bug #7: 0.29 * 100 == 28.999999999999996 in floats;
    # int() would write 28 (one count low), round() writes 29.
    assert VOLTAGE.to_raw(0.29) == 29


def test_from_raw_applies_decimals():
    assert VOLTAGE.from_raw(1234) == pytest.approx(12.34)
    assert CURRENT.from_raw(500) == pytest.approx(0.5)


def test_register_map_matches_oem_doc():
    assert (VOLTAGE.address, VOLTAGE.decimals) == (0x0030, 2)
    assert (CURRENT.address, CURRENT.decimals) == (0x0031, 3)
    # OCP is 3 decimal places, matching CURRENT's amperage-display format (the user
    # manual's display-resolution table gives <10A: 1mA steps) -- not 2 like
    # voltage/OVP. Confirmed against a real unit: raw register 150 read back as
    # 0.150 A on the panel, not 1.50 A.
    assert (OCP.address, OCP.decimals) == (0x0021, 3)
    assert (OPP.address, OPP.decimals, OPP.words) == (0x0022, 2, 2)
    assert (POWER_DISPLAY.address, POWER_DISPLAY.decimals, POWER_DISPLAY.words) == (0x0012, 3, 2)


def test_ocp_scale_matches_panel_reading():
    # Confirmed against real hardware: writing raw register 150 to 0x0021 shows as
    # 0.150 A on the front panel (3 decimals), not 1.50 A (2 decimals).
    assert OCP.to_raw(0.150) == 150
    assert OCP.from_raw(150) == pytest.approx(0.150)


def test_scaled_register_is_frozen():
    with pytest.raises(Exception):
        VOLTAGE.address = 0  # type: ignore[misc]


def test_out_of_range_error_is_a_value_error():
    assert issubclass(OutOfRangeError, ValueError)
    assert issubclass(OutOfRangeError, HM310TError)

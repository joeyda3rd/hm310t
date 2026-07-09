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
    # Spec bug #5: OCP is 2 decimal places (like voltage/OVP), not 3 (like current).
    assert (OCP.address, OCP.decimals) == (0x0021, 2)
    assert (OPP.address, OPP.decimals, OPP.words) == (0x0022, 2, 2)
    assert (POWER_DISPLAY.address, POWER_DISPLAY.decimals, POWER_DISPLAY.words) == (0x0012, 3, 2)


def test_scaled_register_is_frozen():
    with pytest.raises(Exception):
        VOLTAGE.address = 0  # type: ignore[misc]


def test_out_of_range_error_is_a_value_error():
    assert issubclass(OutOfRangeError, ValueError)
    assert issubclass(OutOfRangeError, HM310TError)

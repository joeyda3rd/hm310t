"""Black-box contract tests against README.md's documented PowerSupply behavior.

Written without reading pyHM310T.py — a failure here means the implementation
disagrees with the documented contract, not that the test is wrong.
"""

import pytest


def test_comm_address_is_in_documented_range(power_supply):
    # README: get_comm_address() "Returns an integer value between 1 and 250."
    address = power_supply.get_comm_address()
    assert isinstance(address, int)
    assert 1 <= address <= 250


def test_protection_status_has_documented_shape(power_supply):
    # README: get_protection_status() "Returns a dictionary with the keys
    # 'isOVP', 'isOCP', 'isOPP', 'isOTP', and 'isSCP'."
    status = power_supply.get_protection_status()
    assert isinstance(status, dict)
    expected_keys = {"isOVP", "isOCP", "isOPP", "isOTP", "isSCP"}
    assert expected_keys.issubset(status.keys())
    for key in expected_keys:
        assert status[key] in (True, False, 0, 1)


def test_display_reads_are_non_negative_numbers(power_supply):
    # README: get_voltage_display/get_current_display/get_power_display each
    # "Returns a float value" reflecting the live display.
    voltage = power_supply.get_voltage_display()
    current = power_supply.get_current_display()
    power = power_supply.get_power_display()
    for value in (voltage, current, power):
        assert isinstance(value, (int, float))
        assert value >= 0


def test_set_voltage_roundtrip(power_supply):
    # README: set_voltage(voltage) "should be a float value between 0 and 30
    # (or set limit)"; get_voltage() "Get the set output voltage."
    power_supply.set_voltage(2.0)
    assert power_supply.get_voltage() == pytest.approx(2.0, abs=0.1)


def test_set_current_roundtrip(power_supply):
    # README: set_current(current) "between 0 and 10 (or set limit)".
    power_supply.set_current(0.5)
    assert power_supply.get_current() == pytest.approx(0.5, abs=0.05)


def test_set_ovp_roundtrip(power_supply):
    # README: set_ovp(ovp) "should be a float value between 0 and 30."
    power_supply.set_ovp(10.0)
    assert power_supply.get_ovp() == pytest.approx(10.0, abs=0.1)


def test_set_ocp_roundtrip(power_supply):
    # README: set_ocp(ocp) "should be a float value between 0 and 10."
    power_supply.set_ocp(2.0)
    assert power_supply.get_ocp() == pytest.approx(2.0, abs=0.05)


def test_set_opp_roundtrip(power_supply):
    # README: set_opp(opp) "should be a float value between 0 and 300."
    power_supply.set_opp(20.0)
    assert power_supply.get_opp() == pytest.approx(20.0, abs=1.0)


def test_voltage_above_documented_limit_is_rejected_or_clamped(power_supply):
    # README says the documented range is 0-30 (or configured limit). Output
    # stays disabled throughout, so no current can flow regardless of what
    # the setpoint register ends up holding -- this only probes whether the
    # library enforces its own documented range.
    try:
        power_supply.set_voltage(31.0)
    except (ValueError, Exception):
        return  # rejecting out-of-range input satisfies the documented contract
    assert power_supply.get_voltage() <= 30.0, (
        "set_voltage(31.0) was accepted without error and without being "
        "clamped to the documented 0-30 range"
    )


def test_voltage_below_zero_is_rejected_or_clamped(power_supply):
    try:
        power_supply.set_voltage(-1.0)
    except (ValueError, Exception):
        return
    assert power_supply.get_voltage() >= 0.0, (
        "set_voltage(-1.0) was accepted without error and without being "
        "clamped to the documented 0-30 range"
    )


def test_invalid_port_raises_communication_error():
    # README's Usage example implies a bad/unreachable port should fail
    # loudly rather than hang or raise something unrelated.
    from pyHM310T import PowerSupply, PowerSupplyCommunicationError

    with pytest.raises(PowerSupplyCommunicationError):
        PowerSupply(port="/dev/ttyUSB99")

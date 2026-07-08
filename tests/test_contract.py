"""Black-box contract tests against README.md's documented PowerSupply behavior.

Written without reading pyHM310T.py — a failure here means the implementation
disagrees with the documented contract, not that the test is wrong.
"""


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

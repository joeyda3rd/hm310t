"""Black-box contract suite that talks to a REAL HM310T.

Every ``@pytest.mark.hardware`` test uses the ``power_supply`` fixture, which
forces the output OFF for the test and restores state after (output-enable
restore runs last). Tests skip cleanly when no device is reachable.

    pytest tests/test_contract.py                    # against /dev/ttyUSB0
    PSU_TEST_PORT=/dev/ttyUSB1 pytest tests/test_contract.py
    PSU_LOAD_ATTACHED=1 pytest tests/test_contract.py -m requires_load
"""

from __future__ import annotations

import os

import pytest

from hm310t import (
    Measurement,
    OutOfRangeError,
    PowerSupply,
    PowerSupplyCommunicationError,
    ProtectionStatus,
)

hardware = pytest.mark.hardware

# The load test energizes the output into a real load; it must be opted into
# explicitly (device rating notwithstanding, this sources real current).
LOAD_ATTACHED = os.environ.get("PSU_LOAD_ATTACHED") == "1"


@hardware
def test_comm_address_in_valid_range(power_supply):
    assert 1 <= power_supply.comm_address <= 250


@hardware
def test_protection_status_shape(power_supply):
    status = power_supply.read_protection_status()
    assert isinstance(status, ProtectionStatus)
    assert isinstance(status.tripped, bool)


@hardware
def test_measurement_is_non_negative(power_supply):
    # Output is forced off by the fixture, so the live readings should sit at ~0
    # and certainly never below zero.
    measurement = power_supply.read_measurement()
    assert isinstance(measurement, Measurement)
    assert measurement.voltage >= 0.0
    assert measurement.current >= 0.0
    assert measurement.power >= 0.0


@hardware
def test_set_voltage_roundtrip(power_supply):
    power_supply.voltage = 3.33
    assert power_supply.voltage == pytest.approx(3.33)


@hardware
def test_set_current_roundtrip(power_supply):
    power_supply.current = 0.250
    assert power_supply.current == pytest.approx(0.250)


@hardware
def test_ovp_roundtrip(power_supply):
    power_supply.ovp = 12.50
    assert power_supply.ovp == pytest.approx(12.50)


@hardware
def test_ocp_roundtrip(power_supply):
    power_supply.ocp = 1.50
    assert power_supply.ocp == pytest.approx(1.50)


@hardware
def test_opp_roundtrip(power_supply):
    power_supply.opp = 120.0
    assert power_supply.opp == pytest.approx(120.0)


@hardware
def test_opp_uses_high_word_first_register_order(power_supply):
    # OPP is a 32-bit value across 0x0022/0x0023, 2 dp: 200.0 -> raw 20000.
    # High word first means 0x0022 holds the high half (0), 0x0023 the low (20000).
    # This pins the byte order confirmed against the unit in Task 0.
    power_supply.opp = 200.0
    assert power_supply.read_raw_register(0x0022) == 0
    assert power_supply.read_raw_register(0x0023) == 20000


@hardware
def test_set_voltage_above_limit_raises(power_supply):
    with pytest.raises(OutOfRangeError):
        power_supply.voltage = power_supply.voltage_limit + 1.0


@hardware
def test_set_voltage_below_zero_raises(power_supply):
    with pytest.raises(OutOfRangeError):
        power_supply.voltage = -1.0


@hardware
def test_output_enable_disable_roundtrip(power_supply):
    # The one designated output test: it actually energizes the terminals, so it
    # keeps setpoints low and GUARANTEES disable in finally. The fixture also
    # forces output off in teardown as a backstop.
    power_supply.voltage = 1.0
    power_supply.current = 0.100
    try:
        power_supply.output_enabled = True
        assert power_supply.output_enabled is True
    finally:
        power_supply.output_enabled = False
    assert power_supply.output_enabled is False


def test_invalid_port_raises_communication_error():
    # Unmarked: runs without hardware. A bad port must surface as our own
    # exception type, not a raw pyserial/pymodbus error.
    with pytest.raises(PowerSupplyCommunicationError):
        PowerSupply(port="/dev/hm310t-nonexistent")


@hardware
@pytest.mark.requires_load
@pytest.mark.skipif(not LOAD_ATTACHED, reason="set PSU_LOAD_ATTACHED=1 with a load wired up")
def test_measurement_under_load(power_supply):
    # Requires a physical load on the terminals. Energizes the output to a modest
    # setpoint, confirms current actually flows, and guarantees disable in finally.
    power_supply.voltage = 5.0
    power_supply.current = 0.500
    try:
        power_supply.output_enabled = True
        measurement = power_supply.read_measurement()
        assert measurement.voltage > 0.0
        assert measurement.current > 0.0
    finally:
        power_supply.output_enabled = False

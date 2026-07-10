"""Hardware-free coverage for the safety-critical fixture teardown.

The ``managed_power_supply`` context manager in conftest.py is what guarantees a
300 W output ends every contract test in a safe, restored state. That logic has
no hardware-free coverage of its own -- these tests give it some, driving it with
the in-memory FakeTransport instead of a real device.
"""

from __future__ import annotations

import pathlib

import pytest
from conftest import managed_power_supply
from test_client import FakeTransport

import hm310t.client
from hm310t import PowerSupply, PowerSupplyCommunicationError

pytest_plugins = ["pytester"]

_CONFTEST_SOURCE = pathlib.Path(__file__).parent.joinpath("conftest.py").read_text()

OUTPUT = 0x0001
SET_VOLTAGE = 0x0030


def _build_psu_with_output_on(monkeypatch, transport_cls=FakeTransport):
    """Build a PowerSupply on a fake transport whose device starts with output ON."""
    created = []

    class Patched(transport_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.registers[OUTPUT] = 1  # device discovered with output already ON
            created.append(self)

    monkeypatch.setattr(hm310t.client, "Transport", Patched)
    psu = PowerSupply(port="fake")
    return psu, created[0]


def test_managed_supply_forces_off_on_entry_and_restores_output_last(monkeypatch):
    psu, transport = _build_psu_with_output_on(monkeypatch)

    with managed_power_supply(psu) as supply:
        assert supply is psu
        # Entry forced the output OFF before the test body ran.
        assert transport.write_log[0] == (OUTPUT, [0])

    # Teardown forced output OFF again *before* touching any setpoint...
    assert transport.write_log[1] == (OUTPUT, [0])
    # ...and re-applied the original output state (ON) as the very LAST write.
    assert transport.write_log[-1] == (OUTPUT, [1])
    assert transport.closed


def test_managed_supply_does_not_reenable_output_after_a_failed_restore(monkeypatch):
    class VoltageRestoreFails(FakeTransport):
        def write_register(self, address, value):
            if address == SET_VOLTAGE:
                raise PowerSupplyCommunicationError("simulated set-voltage failure")
            return super().write_register(address, value)

    psu, transport = _build_psu_with_output_on(monkeypatch, VoltageRestoreFails)

    # Baseline output was ON, but a setpoint restore fails. Teardown must NOT
    # re-energize into a degraded state: it leaves the output OFF, closes the port,
    # and surfaces the failure as an AssertionError (never a silent pass).
    with pytest.raises(AssertionError, match="voltage"):
        with managed_power_supply(psu):
            pass

    output_writes = [value for addr, value in transport.write_log if addr == OUTPUT]
    assert (OUTPUT, [1]) not in transport.write_log  # output was NOT re-enabled
    assert output_writes[-1] == [0]  # teardown left it OFF
    assert transport.registers[OUTPUT] == 0  # device physically off
    assert transport.closed


def test_managed_supply_skips_setpoint_restore_when_teardown_force_off_fails(monkeypatch):
    class TeardownOffFails(FakeTransport):
        arm = False  # when armed, the output-OFF write fails (simulates a teardown comms loss)

        def write_register(self, address, value):
            if address == OUTPUT and value == 0 and self.arm:
                raise PowerSupplyCommunicationError("simulated teardown force-off failure")
            return super().write_register(address, value)

    psu, transport = _build_psu_with_output_on(monkeypatch, TeardownOffFails)

    # The teardown's force-off fails. Setpoints must NOT be written to a possibly-live
    # output; the failure must still surface and the port must still close.
    with pytest.raises(AssertionError, match="output-off"):
        with managed_power_supply(psu):
            transport.arm = True  # make the *teardown* force-off (not the entry one) fail

    setpoint_regs = {0x0020, 0x0021, 0x0022, 0x0030, 0x0031}
    assert not any(addr in setpoint_regs for addr, _ in transport.write_log)
    assert (OUTPUT, [1]) not in transport.write_log  # output was never re-enabled
    assert transport.registers[OUTPUT] == 0  # device left physically off
    assert transport.closed


def _assert_power_supply_fixture_outcome(pytester, exc_name, **expected_outcomes):
    """Run the real ``power_supply`` fixture in an isolated pytest process against a
    PowerSupply() constructor that always raises ``exc_name``, and assert the
    resulting pass/skip/error outcome."""
    pytester.makeconftest(_CONFTEST_SOURCE)
    pytester.makepyfile(f"""
        import pytest
        from hm310t import {exc_name}

        @pytest.fixture(autouse=True)
        def _make_powersupply_raise(monkeypatch):
            import conftest

            def _raise(*args, **kwargs):
                raise {exc_name}("simulated")

            monkeypatch.setattr(conftest, "PowerSupply", _raise)

        def test_dummy(power_supply):
            pass
        """)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(**expected_outcomes)


def test_power_supply_fixture_skips_on_communication_error(pytester):
    # The ordinary "nothing plugged in" case must still skip cleanly.
    _assert_power_supply_fixture_outcome(pytester, "PowerSupplyCommunicationError", skipped=1)


def test_power_supply_fixture_fails_loudly_on_incompatible_device(pytester):
    # A wrong-model/firmware device (or any other constructor bug) must fail the
    # test, not be swallowed as "no device reachable."
    _assert_power_supply_fixture_outcome(pytester, "IncompatibleDeviceError", errors=1)

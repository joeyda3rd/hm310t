"""Hardware-free unit tests for PowerSupply against a fake Transport."""

from __future__ import annotations

import pytest

import hm310t.client
from hm310t import (
    IncompatibleDeviceError,
    Measurement,
    OutOfRangeError,
    PowerSupply,
    PowerSupplyCommunicationError,
    ProtectionStatus,
)


class FakeTransport:
    """In-memory stand-in for hm310t.transport.Transport (same interface)."""

    def __init__(self, port, baudrate=9600, slave=1, timeout=1.0):
        self.slave = slave
        self.closed = False
        self.fail_reads = False
        self.fail_writes = False
        self.read_log = []  # (address, count)
        self.write_log = []  # (address, [values]) -- single-value list = FC06, longer = FC16
        self.registers = {
            0x0001: 0,
            0x0002: 0,
            0x0003: 3010,
            0x0005: 0x0233,
            0x0010: 0,
            0x0011: 0,
            0x0012: 0,
            0x0013: 0,
            0x0020: 0,
            0x0021: 0,
            0x0022: 0,
            0x0023: 0,
            0x0030: 0,
            0x0031: 0,
            0x9999: 1,
        }

    def connect(self):
        pass

    def close(self):
        self.closed = True

    def read_registers(self, address, count):
        if self.fail_reads:
            raise PowerSupplyCommunicationError("simulated read failure")
        self.read_log.append((address, count))
        return [self.registers[address + i] for i in range(count)]

    def read_register(self, address):
        return self.read_registers(address, 1)[0]

    def write_register(self, address, value):
        if self.fail_writes:
            raise PowerSupplyCommunicationError("simulated write failure")
        self.write_log.append((address, [value]))
        self.registers[address] = value

    def write_registers(self, address, values):
        if self.fail_writes:
            raise PowerSupplyCommunicationError("simulated write failure")
        self.write_log.append((address, list(values)))
        for i, value in enumerate(values):
            self.registers[address + i] = value


@pytest.fixture
def fake_transports(monkeypatch):
    """Patch Transport inside client.py; returns the list of created fakes."""
    created = []

    def factory(port, baudrate=9600, slave=1, timeout=1.0):
        transport = FakeTransport(port, baudrate=baudrate, slave=slave, timeout=timeout)
        created.append(transport)
        return transport

    monkeypatch.setattr(hm310t.client, "Transport", factory)
    return created


@pytest.fixture
def psu(fake_transports):
    supply = PowerSupply(port="fake")
    transport = fake_transports[0]
    transport.read_log.clear()  # drop the constructor's capacity-check read
    transport.write_log.clear()
    return supply


def test_init_checks_decimal_capacity_and_accepts_matching_device(fake_transports):
    PowerSupply(port="fake")
    assert (0x0005, 1) in fake_transports[0].read_log


def test_init_checks_specification_register(fake_transports):
    PowerSupply(port="fake")
    assert (0x0003, 1) in fake_transports[0].read_log


def test_init_rejects_mismatched_specification(monkeypatch):
    # 0x0003 encodes the rating (3010 = 30 V / 10 A). An HM305 (30 V / 5 A -> 3005)
    # reports the SAME decimals as an HM310T and passes the 0x0005 check; the
    # specification check is what rejects it -- and it must close the transport (bug #1).
    created = []

    class WrongSpec(FakeTransport):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.registers[0x0003] = 3005
            created.append(self)

    monkeypatch.setattr(hm310t.client, "Transport", WrongSpec)
    with pytest.raises(IncompatibleDeviceError):
        PowerSupply(port="fake")
    assert created[0].closed


def test_init_rejects_mismatched_decimal_capacity(monkeypatch, fake_transports):
    class WrongCapacity(FakeTransport):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.registers[0x0005] = 0x0223  # current reported as 2dp, we require 3

    monkeypatch.setattr(hm310t.client, "Transport", WrongCapacity)
    with pytest.raises(IncompatibleDeviceError):
        PowerSupply(port="fake")


def test_init_closes_transport_when_verification_fails(monkeypatch):
    # Spec bug #1: the old code leaked the serial handle when the post-connect
    # read failed (device off), masking the real error on retry loops.
    created = []

    class FailingReads(FakeTransport):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fail_reads = True
            created.append(self)

    monkeypatch.setattr(hm310t.client, "Transport", FailingReads)
    with pytest.raises(PowerSupplyCommunicationError):
        PowerSupply(port="fake")
    assert created[0].closed


def test_init_closes_transport_when_capacity_mismatches(monkeypatch):
    created = []

    class WrongCapacity(FakeTransport):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.registers[0x0005] = 0x0223
            created.append(self)

    monkeypatch.setattr(hm310t.client, "Transport", WrongCapacity)
    with pytest.raises(IncompatibleDeviceError):
        PowerSupply(port="fake")
    assert created[0].closed


def test_init_closes_transport_when_connect_raises(monkeypatch):
    created = []

    class FailingConnect(FakeTransport):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

        def connect(self):
            raise PowerSupplyCommunicationError("no such port")

    monkeypatch.setattr(hm310t.client, "Transport", FailingConnect)
    with pytest.raises(PowerSupplyCommunicationError):
        PowerSupply(port="fake")
    assert created[0].closed


def test_context_manager_closes_transport(fake_transports):
    with PowerSupply(port="fake") as supply:
        assert isinstance(supply, PowerSupply)
    assert fake_transports[0].closed


def test_voltage_setpoint_write_rounds_not_truncates(psu, fake_transports):
    # Spec bug #7: 0.29 * 100 == 28.999999999999996; int() writes 28, round() writes 29.
    psu.voltage = 0.29
    assert fake_transports[0].write_log == [(0x0030, [29])]


def test_scaled_reads(psu, fake_transports):
    fake_transports[0].registers[0x0030] = 1234
    fake_transports[0].registers[0x0031] = 500
    assert psu.voltage == pytest.approx(12.34)
    assert psu.current == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("voltage", 31.0),
        ("voltage", -1.0),
        ("current", 11.0),
        ("current", -0.1),
        ("ovp", 31.0),
        ("ocp", 11.0),
        ("opp", 301.0),
        ("comm_address", 0),
        ("comm_address", 251),
    ],
)
def test_out_of_range_setpoints_raise_and_write_nothing(psu, fake_transports, name, value):
    with pytest.raises(OutOfRangeError):
        setattr(psu, name, value)
    assert fake_transports[0].write_log == []


def test_opp_write_is_one_atomic_fc16(psu, fake_transports):
    psu.opp = 200.0
    assert fake_transports[0].write_log == [(0x0022, [0, 20000])]


def test_opp_read_is_one_batched_read(psu, fake_transports):
    fake_transports[0].registers[0x0022] = 0
    fake_transports[0].registers[0x0023] = 20000
    assert psu.opp == pytest.approx(200.0)
    assert fake_transports[0].read_log == [(0x0022, 2)]


def test_read_measurement_is_one_batched_read(psu, fake_transports):
    # Spec bug #4: the old two-call read could tear a live 32-bit power value.
    transport = fake_transports[0]
    transport.registers.update({0x0010: 500, 0x0011: 1500, 0x0012: 1, 0x0013: 34464})
    measurement = psu.read_measurement()
    assert transport.read_log == [(0x0010, 4)]
    assert measurement == Measurement(voltage=5.0, current=1.5, power=100.0)


def test_output_enabled_roundtrip(psu, fake_transports):
    psu.output_enabled = True
    assert fake_transports[0].write_log == [(0x0001, [1])]
    assert psu.output_enabled is True


def test_output_enabled_read_failure_raises(psu, fake_transports):
    # Spec bug #2: a comms failure must not read as "confirmed safely off".
    fake_transports[0].fail_reads = True
    with pytest.raises(PowerSupplyCommunicationError):
        _ = psu.output_enabled


def test_protection_status_decodes_bits(psu, fake_transports):
    fake_transports[0].registers[0x0002] = 0b10101
    status = psu.read_protection_status()
    assert status == ProtectionStatus(
        is_ovp=True, is_ocp=False, is_opp=True, is_otp=False, is_scp=True
    )
    assert status.tripped is True
    fake_transports[0].registers[0x0002] = 0
    assert psu.read_protection_status().tripped is False


def test_comm_address_setter_retargets_transport(psu, fake_transports):
    psu.comm_address = 5
    assert fake_transports[0].write_log == [(0x9999, [5])]
    assert fake_transports[0].slave == 5


def test_read_raw_register_escape_hatch(psu, fake_transports):
    fake_transports[0].registers[0x0004] = 1234
    assert psu.read_raw_register(0x0004) == 1234


def test_output_enabled_rejects_non_bool(psu, fake_transports):
    # Safety (adversarial review): bool("false") is True, so a coerced value could
    # ENABLE a 300 W output. Only a real bool is accepted; nothing else writes.
    for bad in ("false", "0", 0.0, 2):
        with pytest.raises(TypeError):
            psu.output_enabled = bad
    assert fake_transports[0].write_log == []


def test_comm_address_rejects_non_int(psu, fake_transports):
    for bad in (1.5, "5", True):
        with pytest.raises(TypeError):
            psu.comm_address = bad
    assert fake_transports[0].write_log == []


def test_constructor_rejects_limits_above_device_rating(fake_transports):
    # The 0x0003 check confirms a 30 V / 10 A HM310T, so a higher software ceiling is a bug.
    with pytest.raises(OutOfRangeError):
        PowerSupply(port="fake", voltage_limit=35.0)
    with pytest.raises(OutOfRangeError):
        PowerSupply(port="fake", current_limit=20.0)


def test_voltage_setter_rejects_value_that_rounds_above_fractional_limit(fake_transports):
    # voltage_limit=5.009 has more precision than the register's 2dp resolution.
    # A request at exactly that limit must not round UP to raw 501 (5.01 V) and write it.
    psu = PowerSupply(port="fake", voltage_limit=5.009)
    with pytest.raises(OutOfRangeError):
        psu.voltage = 5.009
    assert fake_transports[0].write_log == []


def test_current_setter_rejects_value_that_rounds_above_fractional_limit(fake_transports):
    # current_limit=1.2349 has more precision than the register's 3dp resolution.
    psu = PowerSupply(port="fake", current_limit=1.2349)
    with pytest.raises(OutOfRangeError):
        psu.current = 1.2349
    assert fake_transports[0].write_log == []


def test_setter_write_failure_propagates(psu, fake_transports):
    # Bug #8 at the client layer: a transport write failure must raise, never be swallowed.
    fake_transports[0].fail_writes = True
    with pytest.raises(PowerSupplyCommunicationError):
        psu.voltage = 5.0


def test_numeric_setters_reject_bool_and_non_numbers(psu, fake_transports):
    # Adversarial review: `psu.voltage = True` passes 0 <= 1 <= 30 and would silently
    # write 1.00 V. Reject bool and non-numbers on all five numeric setpoints; write nothing.
    for name in ("voltage", "current", "ovp", "ocp", "opp"):
        for bad in (True, False, "5", None):
            with pytest.raises(TypeError):
                setattr(psu, name, bad)
    assert fake_transports[0].write_log == []


def test_constructor_rejects_invalid_slave(fake_transports):
    # slave is the Modbus unit id stamped on every frame; slave=0 is broadcast and
    # slave>250 overflows pymodbus. Validate it like comm_address does.
    with pytest.raises(OutOfRangeError):
        PowerSupply(port="fake", slave=0)
    with pytest.raises(OutOfRangeError):
        PowerSupply(port="fake", slave=999)
    with pytest.raises(TypeError):
        PowerSupply(port="fake", slave=True)


def test_exit_disables_output_when_block_raises(fake_transports):
    # An exception unwinding out of the `with` block is an error path: __exit__ must
    # fail safe and disable the output (a `with` implies safe teardown on error).
    with pytest.raises(RuntimeError):
        with PowerSupply(port="fake") as psu:
            psu.output_enabled = True
            raise RuntimeError("boom")
    transport = fake_transports[0]
    output_writes = [value for addr, value in transport.write_log if addr == 0x0001]
    assert output_writes[-1] == [0]  # last output write forced it OFF
    assert transport.closed


def test_exit_leaves_output_untouched_on_clean_exit(fake_transports):
    # A clean exit honors the "leave the output as you set it" philosophy -- no
    # implicit output-off write is issued.
    with PowerSupply(port="fake") as psu:
        psu.output_enabled = True
    transport = fake_transports[0]
    output_writes = [value for addr, value in transport.write_log if addr == 0x0001]
    assert output_writes == [[1]]  # only the deliberate enable; teardown added nothing
    assert transport.closed

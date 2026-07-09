"""Hardware-free unit tests for PowerSupply against a fake Transport."""

from __future__ import annotations

import pytest

import hm310t.client
from hm310t import IncompatibleDeviceError, PowerSupply, PowerSupplyCommunicationError


class FakeTransport:
    """In-memory stand-in for hm310t.transport.Transport (same interface)."""

    def __init__(self, port, baudrate=9600, slave=1, timeout=1.0):
        self.slave = slave
        self.closed = False
        self.fail_reads = False
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
        self.write_log.append((address, [value]))
        self.registers[address] = value

    def write_registers(self, address, values):
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

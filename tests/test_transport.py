"""Hardware-free tests for the Modbus I/O layer, with pymodbus mocked out."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pymodbus.exceptions import ModbusException

import hm310t.transport
from hm310t.exceptions import PowerSupplyCommunicationError
from hm310t.transport import Transport


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock()
    client.connect.return_value = True
    monkeypatch.setattr(hm310t.transport, "ModbusSerialClient", MagicMock(return_value=client))
    return client


def test_connect_failure_raises(mock_client):
    mock_client.connect.return_value = False
    with pytest.raises(PowerSupplyCommunicationError):
        Transport("/dev/ttyUSB0").connect()


def test_connect_exception_raises_typed_error(mock_client):
    # pymodbus 3.2.2 returns False on a bad port, but "every transport failure
    # raises the typed error" must hold even if a pymodbus version raises here
    # (CI installs the latest 3.x, and the invalid-port contract test runs there).
    mock_client.connect.side_effect = OSError("port disappeared")
    with pytest.raises(PowerSupplyCommunicationError):
        Transport("/dev/ttyUSB0").connect()


def test_read_success_returns_register_values(mock_client):
    response = MagicMock()
    response.isError.return_value = False
    response.registers = [1234, 500]
    mock_client.read_holding_registers.return_value = response
    t = Transport("/dev/ttyUSB0")
    assert t.read_registers(0x0010, 2) == [1234, 500]
    assert t.read_register(0x0010) == 1234
    mock_client.read_holding_registers.assert_called_with(0x0010, count=1, slave=1)


def test_error_response_raises_typed_exception(mock_client):
    # Spec bug #3: the old code printed and returned None on error responses.
    mock_client.read_holding_registers.return_value.isError.return_value = True
    with pytest.raises(PowerSupplyCommunicationError):
        Transport("/dev/ttyUSB0").read_register(0x0030)


def test_modbus_exception_raises_typed_exception(mock_client):
    # Spec bug #8: catch the pymodbus hierarchy broadly, raise one typed error.
    mock_client.write_register.side_effect = ModbusException("io failure")
    with pytest.raises(PowerSupplyCommunicationError):
        Transport("/dev/ttyUSB0").write_register(0x0030, 500)


def test_non_modbus_exception_raises_typed_error(mock_client):
    # pyserial-level failures (e.g. USB unplugged mid-read) are not ModbusExceptions
    # but must still surface as the typed error (global constraint: no untyped escapes).
    mock_client.read_holding_registers.side_effect = OSError("device unplugged")
    with pytest.raises(PowerSupplyCommunicationError):
        Transport("/dev/ttyUSB0").read_register(0x0030)


def test_write_error_response_raises(mock_client):
    mock_client.write_registers.return_value.isError.return_value = True
    with pytest.raises(PowerSupplyCommunicationError):
        Transport("/dev/ttyUSB0").write_registers(0x0022, [0, 20000])


def test_writes_use_configured_slave(mock_client):
    response = MagicMock()
    response.isError.return_value = False
    mock_client.write_register.return_value = response
    t = Transport("/dev/ttyUSB0", slave=3)
    t.write_register(0x0030, 500)
    mock_client.write_register.assert_called_with(0x0030, 500, slave=3)


def test_no_dead_method_kwarg(monkeypatch):
    # Spec bug #6: method='rtu' is not a real ModbusSerialClient parameter in pymodbus 3.2.2.
    ctor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(hm310t.transport, "ModbusSerialClient", ctor)
    Transport("/dev/ttyUSB0", baudrate=115200)
    assert "method" not in ctor.call_args.kwargs

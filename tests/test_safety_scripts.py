"""Hardware-free safety tests for standalone examples and diagnostic scripts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, error: bool = False):
        self._error = error

    def isError(self):
        return self._error


class RawClient:
    def __init__(self, snapshots_available: bool = True, fail_voltage_restore: bool = False):
        self.snapshots_available = snapshots_available
        self.fail_voltage_restore = fail_voltage_restore
        self.closed = False
        self.writes: list[tuple[int, list[int]]] = []

    def connect(self):
        return True

    def close(self):
        self.closed = True

    def read_holding_registers(self, address, count=1, slave=1):
        if address == 0x0001:
            return _response([0])
        if address == 0x0030 and not self.snapshots_available:
            return None
        if address == 0x0022 and count == 2 and not self.snapshots_available:
            return None
        if address == 0x0030:
            return _response([500])
        if address == 0x0022 and count == 2:
            return _response([0, 3000])
        return _response([0] * count)

    def write_register(self, address, value, slave=1):
        self.writes.append((address, [value]))
        return Response(self.fail_voltage_restore and address == 0x0030 and value == 500)

    def write_registers(self, address, values, slave=1):
        self.writes.append((address, list(values)))
        return Response()


def _response(registers):
    response = Response()
    response.registers = registers
    return response


def test_characterize_rejects_missing_snapshots_before_configuration_writes(monkeypatch):
    characterize = _load_module("characterize_safety", "tools/characterize.py")
    client = RawClient(snapshots_available=False)
    monkeypatch.setattr(characterize, "ModbusSerialClient", lambda **kwargs: client)

    with pytest.raises(RuntimeError, match="snapshot"):
        characterize.main()

    assert client.writes == [(0x0001, [0])]
    assert client.closed is True


def test_characterize_restores_opp_and_closes_after_voltage_restore_failure(monkeypatch):
    characterize = _load_module("characterize_restore_safety", "tools/characterize.py")
    client = RawClient(fail_voltage_restore=True)
    monkeypatch.setattr(characterize, "ModbusSerialClient", lambda **kwargs: client)

    with pytest.raises(RuntimeError, match="cleanup"):
        characterize.main()

    output_off = client.writes.index((0x0001, [0]))
    voltage_restore = client.writes.index((0x0030, [500]))
    opp_restore = client.writes.index((0x0022, [0, 3000]))
    assert output_off < voltage_restore < opp_restore
    assert client.closed is True


class SmokeSupply:
    def __init__(self, port, fail_restore: bool = True):
        self.closed = False
        self.fail_restore = fail_restore
        self.output_enabled = False
        self._values = {
            "voltage": 5.0,
            "current": 0.5,
            "ovp": 30.0,
            "ocp": 1.0,
            "opp": 30.0,
        }

    def close(self):
        self.closed = True

    def __getattr__(self, name):
        if name in self._values:
            return self._values[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in {"closed", "fail_restore", "output_enabled", "_values"}:
            object.__setattr__(self, name, value)
        elif name in self._values:
            baseline = {"voltage": 5.0, "current": 0.5, "ovp": 30.0, "ocp": 1.0, "opp": 30.0}
            if self.fail_restore and value == baseline[name]:
                raise RuntimeError("simulated restore failure")
            self._values[name] = value
        else:
            object.__setattr__(self, name, value)


def test_smoke_write_fails_when_baseline_restore_fails(monkeypatch, capsys):
    smoke_write = _load_module("smoke_write_safety", "tools/smoke_write.py")
    supply = SmokeSupply("fake")
    monkeypatch.setattr(smoke_write, "PowerSupply", lambda port: supply)
    monkeypatch.setattr(smoke_write.time, "sleep", lambda seconds: None)

    with pytest.raises(SystemExit) as exit_info:
        smoke_write.main()

    assert exit_info.value.code == 1
    assert "SMOKE PASS" not in capsys.readouterr().out
    assert supply.closed is True


def test_smoke_write_reports_success_after_restoring_every_setting(monkeypatch, capsys):
    smoke_write = _load_module("smoke_write_success", "tools/smoke_write.py")
    supply = SmokeSupply("fake", fail_restore=False)
    monkeypatch.setattr(smoke_write, "PowerSupply", lambda port: supply)
    monkeypatch.setattr(smoke_write.time, "sleep", lambda seconds: None)

    smoke_write.main()

    assert "SMOKE PASS" in capsys.readouterr().out
    assert supply._values == {"voltage": 5.0, "current": 0.5, "ovp": 30.0, "ocp": 1.0, "opp": 30.0}
    assert supply.closed is True


class ExampleSupply:
    def __init__(self, port):
        self.events: list[tuple[str, object]] = []
        self._output_enabled = True
        self._values = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.events.append(("close", None))

    @property
    def output_enabled(self):
        return self._output_enabled

    @output_enabled.setter
    def output_enabled(self, value):
        self.events.append(("output_enabled", value))
        self._output_enabled = value

    def __getattr__(self, name):
        if name in {"voltage", "current", "ovp", "ocp", "opp"}:
            return self._values.get(name, 0.0)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in {"events", "_output_enabled", "_values"}:
            object.__setattr__(self, name, value)
        elif name in {"voltage", "current", "ovp", "ocp", "opp"}:
            self.events.append((name, value))
            self._values[name] = value
        else:
            object.__setattr__(self, name, value)

    def read_measurement(self):
        return type("Measurement", (), {"voltage": 0.0, "current": 0.0, "power": 0.0})()

    def read_protection_status(self):
        return type("Protection", (), {"tripped": False})()


def test_basic_example_disables_output_before_configuration(monkeypatch):
    basic_usage = _load_module("basic_usage_safety", "examples/basic_usage.py")
    supply = ExampleSupply("fake")
    monkeypatch.setattr(basic_usage, "PowerSupply", lambda port: supply)

    basic_usage.main()

    first_configuration = next(
        index
        for index, (name, _) in enumerate(supply.events)
        if name in {"voltage", "current", "ovp", "ocp", "opp"}
    )
    assert supply.events[first_configuration - 1] == ("output_enabled", False)

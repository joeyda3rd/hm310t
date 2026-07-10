# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-07-10

Bug-fix release: four issues from an external code review, and a real decimal-scaling
bug found while running the hardware contract suite against a physical unit.

### Fixed
- `voltage`/`current` setters could accept a value that rounds past a fractional
  software ceiling (`voltage_limit`/`current_limit`) after quantizing to the
  register's fixed-point resolution, e.g. `voltage_limit=5.009` letting a request
  at exactly that value round up to a raw write of 5.01 V. `_write_scaled` now
  re-checks the post-rounding value before writing.
- `Transport.close()` didn't wrap failures in `PowerSupplyCommunicationError` like
  every other I/O method, and a close() failure during exception unwinding (in
  `PowerSupply.__init__`'s cleanup path or `__exit__`'s `finally`) could replace
  the real error being propagated. Close failures are now wrapped consistently and
  suppressed during unwinding so the original exception stays primary; a close
  failure on a clean exit still surfaces.
- The hardware contract suite's `power_supply` fixture caught bare `Exception`
  around device construction, so an `IncompatibleDeviceError` (wrong model or
  firmware) or any unexpected bug was silently reported as "no device reachable"
  instead of failing the test. Now skips only on `PowerSupplyCommunicationError`.
- `test_measurement_under_load` was missing the `@hardware` marker despite using
  the real-hardware fixture, so `pytest -m hardware` silently missed it.
- **`OCP` (0x0021) was scaled at 2 decimal places; it's actually 3, matching
  `CURRENT`'s convention.** The OEM Modbus doc's own register table states 2dp
  for OCP, which is wrong -- confirmed against real hardware two independent
  ways (a raw-register write read back on the front panel, and a deliberate
  panel-set-then-read-back calibration). Every prior `ocp` write was off by a
  factor of 10 from what was intended. `_OCP_RANGE` (0-10 A) is unaffected.

### Changed
- README's OEM register table and notes corrected to match the `OCP` fix, plus a
  new "Known OEM documentation errors" section cataloging every internal
  contradiction found in `OEM-docs/Modbus.pdf` (its function-code claim
  contradicting its own Table 8.1, its slave-address-range claim, OPP's
  implausible 16-bit range on a 32-bit register, and the page-5 worked example's
  arithmetic contradicting its own decimal-capacity table).
- `tools/smoke_write.py`'s OCP round-trip tolerance was still computed from the
  old (wrong) 2dp scale; fixed to 3dp so it can't mask a regression of the above.

## [0.1.0] - 2026-07-09

First packaged release: a reorganization of the original flat `pyHM310T.py`
script into an installable `hm310t` package with a property-based API, a
hardware-free unit suite, and a hardware contract suite.

### Added
- `hm310t` package with a two-layer design: `transport.py` (raw Modbus RTU I/O)
  and `client.py` (`PowerSupply`, the public property-based API).
- Property API: `voltage`, `current`, `ovp`, `ocp`, `opp`, `output_enabled`,
  `comm_address`, plus `read_measurement()`, `read_protection_status()`, and a
  `read_raw_register()` escape hatch.
- Typed results `Measurement` and `ProtectionStatus` (with a `.tripped` flag).
- Exception taxonomy under `HM310TError`: `PowerSupplyCommunicationError`,
  `OutOfRangeError`, and `IncompatibleDeviceError`.
- Connect-time device verification: rejects non-HM310T units via the
  specification (`0x0003`) and decimal-capacity (`0x0005`) registers.
- Atomic multi-register reads/writes via FC16 (verified on the real unit),
  eliminating the torn-read/torn-write windows of the old two-call approach.
- Ships PEP 561 type information (`py.typed`) so downstream code type-checks.
- Hardware-free unit suite (`tests/test_registers.py`, `tests/test_transport.py`,
  `tests/test_client.py`) driven by an in-memory fake transport.
- Hardware contract suite (`tests/test_contract.py`) that talks to a real device
  and skips cleanly when none is attached, plus `tests/test_conftest_safety.py`,
  which covers the safety-critical fixture teardown without hardware.
- Examples (`examples/basic_usage.py`, `examples/tui_dashboard.py`), a read-only
  register scanner (`tools/scan_registers.py`), and an opt-in write smoke test
  (`tools/smoke_write.py`) that round-trips each setpoint on a real device with the
  output kept off.

### Changed
- Minimum Python is now **3.10** (was 3.7).
- Setpoint scaling rounds instead of truncating, fixing off-by-one writes such as
  `0.29 V` (bug #7).
- Strict-`bool` `output_enabled` setter: assigning a non-`bool` raises `TypeError`
  rather than coercing (a truthy string could otherwise energize the output). The
  numeric setpoint setters (`voltage`, `current`, `ovp`, `ocp`, `opp`) likewise
  reject `bool` and non-numbers — `psu.voltage = True` no longer silently writes 1 V.
- The constructor validates `slave` (the Modbus unit id) to 1–250, matching
  `comm_address`; `slave=0` (broadcast) and out-of-range ids are rejected up front.
- `__exit__` now disables the output as a fail-safe when the `with` block exits via
  an exception. A clean exit still leaves the output as set.
- Minimum pyserial is pinned to `>=3.5` (the proven version).

### Fixed
- The serial handle is no longer leaked when connect or post-connect verification
  fails (bug #1).
- Communication failures raise instead of being swallowed and returning `None`
  (bugs #2, #8).
- Short or malformed Modbus read responses now raise `PowerSupplyCommunicationError`
  instead of surfacing as an `IndexError` in the client layer.
- Dropped the dead `method='rtu'` keyword argument used against pymodbus 3.x.
- Pin `pymodbus<3.10` (was `<4.0`): pymodbus 3.10.0 renamed the `slave=` keyword
  argument used on every read/write to `device_id=` with no compatibility shim,
  so `pip install hm310t` resolved a pymodbus that made every register operation
  raise `PowerSupplyCommunicationError`.
- Add `MANIFEST.in` so the sdist includes `tests/conftest.py`; without it the
  unit tests packaged in the sdist have no fixtures to import.

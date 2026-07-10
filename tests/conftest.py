"""Shared fixtures for the hardware contract suite.

The ``power_supply`` fixture talks to a REAL HM310T (default /dev/ttyUSB0,
override with PSU_TEST_PORT) and skips cleanly when none is reachable. It
snapshots device state, forces the output OFF for the duration of every test,
and restores everything afterward -- output-enable restore runs LAST, because
it is the safety-critical step. This device produces real voltage and current.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from hm310t import PowerSupply, PowerSupplyCommunicationError

PSU_PORT = os.environ.get("PSU_TEST_PORT", "/dev/ttyUSB0")


def _snapshot_state(psu: PowerSupply) -> dict[str, object]:
    """Capture every setting a test might disturb, so teardown can put it back."""
    return {
        "voltage": psu.voltage,
        "current": psu.current,
        "ovp": psu.ovp,
        "ocp": psu.ocp,
        "opp": psu.opp,
        "output_enabled": psu.output_enabled,
    }


def _restore_state(psu: PowerSupply, baseline: dict[str, object]) -> list[str]:
    """Restore a snapshot, output-enable LAST. Returns a list of failure messages.

    Each restore is isolated in its own try/except so one failure can't skip the
    rest -- above all it must not skip re-applying the output state. Setpoints and
    trip points are restored while the output is forced off; the baseline output
    state is re-applied only at the very end, once the setpoints are safe again.
    """
    errors: list[str] = []

    # Force output off before touching setpoints, so nothing energizes mid-restore.
    output_is_off = False
    try:
        psu.output_enabled = False
        output_is_off = True
    except Exception as exc:  # noqa: BLE001 -- collect, never abort the restore
        errors.append(f"output-off: {exc!r}")

    # Only restore setpoints once the output is CONFIRMED off -- never write
    # setpoints to a possibly-live output (mirrors the entry-side discipline).
    if output_is_off:
        for name in ("ovp", "ocp", "opp", "voltage", "current"):
            try:
                setattr(psu, name, baseline[name])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {exc!r}")

    # Safety-critical and LAST. NEVER energize into a degraded restore: only turn the
    # output back ON if every step above succeeded (clean force-off + clean setpoints).
    # Otherwise force it OFF and let `errors` fail the teardown loudly.
    want_on = baseline["output_enabled"] is True and not errors
    try:
        psu.output_enabled = want_on
    except Exception as exc:  # noqa: BLE001
        errors.append(f"output-restore: {exc!r}")

    return errors


@contextmanager
def managed_power_supply(psu: PowerSupply) -> Iterator[PowerSupply]:
    """Snapshot + force-off on entry; restore + close on exit.

    If restore reports any failure, the context raises AssertionError after the
    connection is closed -- a botched restore must never pass silently on a device
    that sources 300 W.
    """
    try:
        baseline = _snapshot_state(psu)
        psu.output_enabled = False
    except BaseException:
        # A failure snapshotting or forcing-off on entry must still close the port.
        psu.close()
        raise

    try:
        yield psu
    finally:
        # close() must run even if _restore_state raises (including a BaseException
        # such as a KeyboardInterrupt mid-teardown) -- never leak the serial handle.
        try:
            errors = _restore_state(psu, baseline)
        finally:
            psu.close()
        if errors:
            raise AssertionError(f"power supply restore failed: {errors}")


@pytest.fixture
def power_supply() -> Iterator[PowerSupply]:
    """A real HM310T with output forced off for the test and state restored after."""
    try:
        psu = PowerSupply(port=PSU_PORT)
    except PowerSupplyCommunicationError as exc:
        pytest.skip(f"no HM310T reachable on {PSU_PORT}: {exc}")
    # IncompatibleDeviceError (wrong model/firmware) and any other unexpected
    # constructor failure must fail the test loudly, not be swallowed as "no device".

    with managed_power_supply(psu) as supply:
        yield supply

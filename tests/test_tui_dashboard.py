"""Hardware-free unit tests for the examples/tui_dashboard.py control panel.

Exercises state transitions, rendering, and the main loop against a fake
Transport and a duck-typed fake curses screen -- no real terminal or hardware
required. tui_dashboard.py lives outside the installed package, so it's loaded
by file path rather than via sys.path surgery.
"""

from __future__ import annotations

import curses
import importlib.util
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

import hm310t.client
from hm310t import Measurement, PowerSupply, PowerSupplyCommunicationError, ProtectionStatus

_MODULE_PATH = Path(__file__).resolve().parent.parent / "examples" / "tui_dashboard.py"
_spec = importlib.util.spec_from_file_location("tui_dashboard", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
tui_dashboard = importlib.util.module_from_spec(_spec)
sys.modules["tui_dashboard"] = tui_dashboard  # dataclasses needs this registered to introspect
_spec.loader.exec_module(tui_dashboard)


class FakeTransport:
    """In-memory stand-in for hm310t.transport.Transport (same interface)."""

    def __init__(self, port, baudrate=9600, slave=1, timeout=1.0):
        self.slave = slave
        self.closed = False
        self.fail_writes = False
        self.registers = {
            0x0001: 0,  # output off
            0x0002: 0,  # protection status
            0x0003: 3010,  # 30 V / 10 A identity
            0x0005: 0x0233,  # V 2dp, A 3dp, W 3dp
            0x0010: 0,
            0x0011: 0,
            0x0012: 0,
            0x0013: 0,
            0x0020: 3000,  # OVP 30.00 V
            0x0021: 1000,  # OCP 1.000 A
            0x0022: 0,  # OPP high word
            0x0023: 3000,  # OPP low word -> 30.00 W
            0x0030: 500,  # voltage setpoint 5.00 V
            0x0031: 500,  # current setpoint 0.500 A
            0x9999: 1,
        }

    def connect(self):
        pass

    def close(self):
        self.closed = True

    def read_registers(self, address, count):
        return [self.registers[address + i] for i in range(count)]

    def read_register(self, address):
        return self.read_registers(address, 1)[0]

    def write_register(self, address, value):
        if self.fail_writes:
            raise PowerSupplyCommunicationError("simulated write failure")
        self.registers[address] = value

    def write_registers(self, address, values):
        if self.fail_writes:
            raise PowerSupplyCommunicationError("simulated write failure")
        for i, value in enumerate(values):
            self.registers[address + i] = value


class FlakyAfterConnectTransport(FakeTransport):
    """Answers the constructor's identity reads, then fails every read after."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._read_calls = 0

    def read_registers(self, address, count):
        self._read_calls += 1
        if self._read_calls > 2:
            raise PowerSupplyCommunicationError("simulated read failure")
        return super().read_registers(address, count)


class FakeScreen:
    """Duck-typed stand-in for curses.window -- just enough for tui_dashboard."""

    def __init__(self, keys, size=(24, 80)):
        self._keys = list(keys)
        self._size = size
        self.nodelay_flags: list[bool] = []

    def nodelay(self, flag):
        self.nodelay_flags.append(flag)

    def getch(self):
        return self._keys.pop(0) if self._keys else -1

    def getmaxyx(self):
        return self._size

    def erase(self):
        pass

    def clear(self):
        pass

    def addstr(self, *args):
        pass

    def refresh(self):
        pass


def _keys(text: str, terminator: int = 13) -> list:
    return [ord(c) for c in text] + [terminator]


def _text(line) -> str:
    return "".join(segment[0] for segment in line)


def _find(lines: list, text: str):
    return next(line for line in lines if _text(line) == text)


def _styles_in(line) -> set:
    return {style for _, style in line}


@pytest.fixture
def fake_transports(monkeypatch):
    created = []

    def factory(port, baudrate=9600, slave=1, timeout=1.0):
        transport = FakeTransport(port, baudrate=baudrate, slave=slave, timeout=timeout)
        created.append(transport)
        return transport

    monkeypatch.setattr(hm310t.client, "Transport", factory)
    return created


@pytest.fixture
def psu(fake_transports):
    return PowerSupply(port="fake")


@pytest.fixture
def device(psu):
    # Poller is never started here -- these tests drive functions directly, not
    # the background thread, so it just serves as the shared mirrored state.
    lock = threading.Lock()
    poller = tui_dashboard.Poller(psu, lock)
    poller.read_once()  # seed values/measurement/protection/output_enabled
    return tui_dashboard.Device(psu, lock, poller)


def _base_state(device: "tui_dashboard.Device") -> "tui_dashboard.PanelState":
    return tui_dashboard.PanelState(
        selected=0,
        place_index=2,  # matches main()'s default: 0.1 V / 0.01 A / 1 W
        status="",
        values=dict(device.poller.values),
        measurement=Measurement(5.0, 0.5, 2.5),
        protection=ProtectionStatus(False, False, False, False, False),
        output_enabled=False,
        enabled_at=None,
        disabled_at=None,
        peak_voltage=0.0,
        peak_current=0.0,
        avg_voltage=0.0,
        avg_current=0.0,
    )


# ---- Poller: setpoint sync + headroom tracking ----------------------------


def test_poller_read_once_reads_all_five_setpoints(device):
    assert device.poller.values == {
        "voltage": 5.0,
        "current": 0.5,
        "ovp": 30.0,
        "ocp": 1.0,
        "opp": 30.0,
    }


def test_poller_read_once_reflects_external_setpoint_changes(psu, device):
    psu.voltage = 7.5  # changed by something other than this panel (front panel, another client)
    device.poller.read_once()
    assert device.poller.values["voltage"] == 7.5


def test_poller_tracks_peak_and_running_average_while_enabled(psu, device, fake_transports):
    transport = fake_transports[0]
    psu.output_enabled = True
    transport.registers[0x0010] = 500  # 5.00 V
    device.poller.read_once()
    assert device.poller.peak_voltage == pytest.approx(5.0)
    assert device.poller.avg_voltage == pytest.approx(5.0)

    transport.registers[0x0010] = 300  # 3.00 V -- lower than the peak
    device.poller.read_once()
    assert device.poller.peak_voltage == pytest.approx(5.0)  # peak holds the higher sample
    assert device.poller.avg_voltage == pytest.approx(4.0)  # mean of 5.0 and 3.0


def test_poller_does_not_accumulate_headroom_while_output_is_off(device, fake_transports):
    fake_transports[0].registers[0x0010] = 500
    device.poller.read_once()  # output stays off (default)
    assert device.poller.peak_voltage == 0.0
    assert device.poller.avg_voltage == 0.0


def test_reset_headroom_zeros_everything(device):
    device.poller.peak_voltage = 9.0
    device.poller.avg_voltage = 5.0
    device.poller.reset_headroom()
    assert device.poller.peak_voltage == 0.0
    assert device.poller.avg_voltage == 0.0
    assert device.poller.avg_current == 0.0


# ---- Timer -----------------------------------------------------------------


def test_fmt_duration_formats_hh_mm_ss():
    assert tui_dashboard._fmt_duration(0) == "00:00:00"
    assert tui_dashboard._fmt_duration(5) == "00:00:05"
    assert tui_dashboard._fmt_duration(3725) == "01:02:05"


def test_elapsed_is_none_before_ever_enabled(device):
    assert tui_dashboard._elapsed(_base_state(device), now=100.0) is None


def test_elapsed_counts_up_while_enabled(device):
    state = replace(_base_state(device), output_enabled=True, enabled_at=100.0)
    assert tui_dashboard._elapsed(state, now=105.5) == pytest.approx(5.5)


def test_elapsed_freezes_after_disable(device):
    state = replace(_base_state(device), output_enabled=False, enabled_at=100.0, disabled_at=106.0)
    assert tui_dashboard._elapsed(state, now=200.0) == pytest.approx(6.0)


def test_initial_enabled_at_seeds_the_timer_when_already_on_at_startup(device):
    device.poller.output_enabled = True
    assert tui_dashboard._initial_enabled_at(device.poller, now=123.0) == 123.0


def test_initial_enabled_at_is_none_when_off_at_startup(device):
    device.poller.output_enabled = False
    assert tui_dashboard._initial_enabled_at(device.poller, now=123.0) is None


# ---- Digit highlight (step-size indicator) ---------------------------------


def test_split_target_digit_isolates_the_tenths_digit():
    segments = tui_dashboard._split_target_digit("     5.00", 0.1)
    assert segments == [("     5.", False), ("0", True), ("0", False)]


def test_split_target_digit_isolates_the_ones_digit():
    segments = tui_dashboard._split_target_digit("     5.00", 1.0)
    assert segments == [("     ", False), ("5", True), (".00", False)]


def test_split_target_digit_falls_back_when_the_digit_does_not_exist():
    # "5.00" has no tens digit to highlight
    assert tui_dashboard._split_target_digit("     5.00", 10.0) == [("     5.00", False)]


def test_setpoint_line_highlights_the_correct_digit(device):
    field = tui_dashboard.FIELDS[0]  # voltage = 5.00, place_index 2 -> step 0.1
    state = _base_state(device)
    line = tui_dashboard._setpoint_line(field, state, selected=True)
    highlighted = [text for text, style in line if style == tui_dashboard.STYLE_NORMAL]
    assert highlighted == ["0"]  # the tenths digit
    assert _text(line).strip().endswith("step 0.10")


def test_setpoint_line_falls_back_cleanly_when_no_such_digit(device):
    field = tui_dashboard.FIELDS[0]
    state = replace(_base_state(device), place_index=0)  # step 10 -> tens digit; 5.00 has none
    line = tui_dashboard._setpoint_line(field, state, selected=True)
    assert not any(style == tui_dashboard.STYLE_NORMAL for _, style in line)


def test_setpoint_line_unselected_has_no_row_highlight(device):
    field = tui_dashboard.FIELDS[1]
    state = _base_state(device)
    line = tui_dashboard._setpoint_line(field, state, selected=False)
    assert _styles_in(line) == {tui_dashboard.STYLE_NORMAL}


# ---- Headroom bars -----------------------------------------------------


def test_bar_ratio_clamps_and_handles_zero_limit():
    assert tui_dashboard._bar_ratio(5.0, 0.0) == 0.0
    assert tui_dashboard._bar_ratio(-5.0, 10.0) == 0.0
    assert tui_dashboard._bar_ratio(50.0, 10.0) == 1.0
    assert tui_dashboard._bar_ratio(5.0, 10.0) == pytest.approx(0.5)


def test_bar_text_fills_proportionally():
    text = tui_dashboard._bar_text(5.0, 10.0)
    assert text == "[" + "▓" * 10 + "░" * 10 + "]"


def test_tick_line_places_peak_and_average_marks():
    line = tui_dashboard._tick_line(peak=20.0, avg=10.0, limit=30.0)
    text = _text(line)
    assert text[14] == "▲"  # 1 + int(20/30 * 20)
    assert text[7] == "·"  # 1 + int(10/30 * 20)
    peak_segment = next(t for t, s in line if s == tui_dashboard.STYLE_ENABLED)
    assert peak_segment == "▲"


def test_tick_line_peak_wins_when_positions_collide():
    line = tui_dashboard._tick_line(peak=15.0, avg=15.0, limit=30.0)
    text = _text(line)
    assert text.count("▲") == 1
    assert "·" not in text


def test_headroom_block_shows_percent_bar_and_peak_avg_captions():
    lines = tui_dashboard._headroom_block("V/OVP", 15.0, 30.0, 20.0, 10.0, "V", 2)
    texts = [_text(line) for line in lines]
    assert texts[0] == "V/OVP  50%"
    assert texts[1] == "[" + "▓" * 10 + "░" * 10 + "]"
    assert "peak 20.00 V (67%)" in texts[3]
    assert "avg 10.00 V (33%)" in texts[3]


# ---- Status styling ----------------------------------------------------


def test_status_style_flags_communication_errors():
    assert tui_dashboard._status_style("Communication error: x") == tui_dashboard.STYLE_TRIPPED
    assert tui_dashboard._status_style("Output enabled") == tui_dashboard.STYLE_NORMAL


# ---- Full-frame render ---------------------------------------------------


def test_render_shows_title_setpoints_and_measurement(device):
    layout = tui_dashboard._render(_base_state(device), now=0.0, width=100)
    assert _text(layout["header"][0]) == "HM310T Control Panel"
    assert _text(_find(layout["header"], "Output: OFF")) == "Output: OFF"
    assert any("SETPOINTS" in _text(line) for line in layout["left"])
    assert any("5.00 V" in _text(line) and "0.500 A" in _text(line) for line in layout["right"])
    assert _text(_find(layout["right"], "OK")) == "OK"


def test_render_returns_header_left_right_footer_sections(device):
    state = _base_state(device)
    layout = tui_dashboard._render(state, now=0.0, width=100)
    assert any("SETPOINTS" in _text(line) for line in layout["left"])
    assert any("PROTECTION" in _text(line) for line in layout["right"])
    assert any(_text(line) == state.status for line in layout["footer"])


def test_render_shows_a_full_width_live_bar_while_enabled(device):
    state = replace(_base_state(device), output_enabled=True, enabled_at=10.0)
    layout = tui_dashboard._render(state, now=10.0 + 3725, width=60)
    bar_line = next(line for line in layout["header"] if tui_dashboard.BOLT in _text(line))
    assert _styles_in(bar_line) == {tui_dashboard.STYLE_LIVE_BAR}
    assert len(_text(bar_line)) == 60  # fills the full row width
    assert "01:02:05" in _text(bar_line)


def test_render_shows_last_run_duration_when_off(device):
    state = replace(_base_state(device), output_enabled=False, enabled_at=10.0, disabled_at=15.0)
    layout = tui_dashboard._render(state, now=999.0, width=100)
    assert _text(_find(layout["header"], "Output: OFF   (last run 00:00:05)"))


def test_render_uses_tripped_style_for_protection_line(device):
    state = replace(
        _base_state(device), protection=ProtectionStatus(True, False, True, False, False)
    )
    layout = tui_dashboard._render(state, now=0.0, width=100)
    line = _find(layout["right"], "TRIPPED: OVP, OPP")
    assert _styles_in(line) == {tui_dashboard.STYLE_TRIPPED}


def test_render_includes_headroom_blocks_for_voltage_and_current(device):
    state = _base_state(device)  # ovp 30.00 V, ocp 1.000 A from the fake transport
    layout = tui_dashboard._render(state, now=0.0, width=100)
    texts = [_text(line) for line in layout["right"]]
    assert any(t.startswith("V/OVP") for t in texts)
    assert any(t.startswith("A/OCP") for t in texts)


# ---- Setpoint editing ----------------------------------------------------


def test_step_increments_and_writes_through_to_the_device(psu, device):
    field = tui_dashboard.FIELDS[0]  # voltage, place_index 2 -> step 0.1
    state = _base_state(device)
    new_state = tui_dashboard._step(state, field, device, field.places[state.place_index])
    assert new_state.values["voltage"] == pytest.approx(5.1)
    assert psu.voltage == pytest.approx(5.1)
    assert new_state.status == "Voltage set to 5.10 V"


def test_apply_updates_the_pollers_mirror_immediately(psu, device):
    field = tui_dashboard.FIELDS[0]
    tui_dashboard._step(_base_state(device), field, device, field.places[2])
    assert device.poller.values["voltage"] == pytest.approx(5.1)


def test_step_out_of_range_reports_the_devices_error_and_keeps_the_cache(psu, device):
    field = tui_dashboard.FIELDS[2]  # ovp, range 0-30, already at the ceiling
    state = _base_state(device)
    new_state = tui_dashboard._step(state, field, device, field.places[state.place_index])
    assert new_state.values["ovp"] == 30.0
    assert "ovp must be between" in new_state.status
    assert psu.ovp == 30.0  # nothing was written


def test_enter_value_parses_and_applies_a_typed_number(psu, device):
    field = tui_dashboard.FIELDS[1]  # current
    screen = FakeScreen(_keys("0.75"))
    new_state = tui_dashboard._enter_value(_base_state(device), field, device, screen)
    assert psu.current == pytest.approx(0.75)
    assert new_state.values["current"] == pytest.approx(0.75)


def test_enter_value_rejects_non_numeric_text(psu, device):
    field = tui_dashboard.FIELDS[1]
    screen = FakeScreen(_keys("abc"))
    new_state = tui_dashboard._enter_value(_base_state(device), field, device, screen)
    assert "Not a number" in new_state.status
    assert psu.current == 0.5


def test_enter_value_cancelled_with_escape(psu, device):
    field = tui_dashboard.FIELDS[1]
    screen = FakeScreen([ord("9"), 27])  # type '9' then Esc
    new_state = tui_dashboard._enter_value(_base_state(device), field, device, screen)
    assert new_state.status == "Cancelled"
    assert psu.current == 0.5


def test_prompt_supports_backspace():
    screen = FakeScreen([ord("1"), ord("2"), 127, ord("3"), 13])  # "12<back>3" -> "13"
    assert tui_dashboard._prompt(screen, "value: ", 5, 2, 20) == "13"


def test_enter_value_prompts_directly_under_the_setpoints_bounded_to_that_column(
    monkeypatch, device
):
    captured = {}

    def fake_prompt(stdscr, prompt, row, col, width):
        captured["row"] = row
        captured["col"] = col
        captured["width"] = width
        return "1.0"

    monkeypatch.setattr(tui_dashboard, "_prompt", fake_prompt)
    field = tui_dashboard.FIELDS[0]
    tui_dashboard._enter_value(_base_state(device), field, device, FakeScreen([]))
    # +1: row 0 (PROMPT_ROW) holds the static context line, the input goes below it
    assert captured["row"] == tui_dashboard.PROMPT_ROW + 1
    assert captured["col"] == tui_dashboard.LEFT_COL
    # Bounded so it never reaches the LIVE READING column on the same rows
    assert captured["width"] == tui_dashboard.PROMPT_WIDTH
    assert tui_dashboard.LEFT_COL + tui_dashboard.PROMPT_WIDTH < tui_dashboard.RIGHT_COL


# ---- Output toggle --------------------------------------------------------


def test_set_output_enable_and_disable(psu, device):
    enabled = tui_dashboard._set_output(_base_state(device), device, True)
    assert psu.output_enabled is True
    assert enabled.output_enabled is True
    assert device.poller.output_enabled is True  # kept in lock-step, not left for the next poll
    assert "latency" in enabled.status
    disabled = tui_dashboard._set_output(enabled, device, False)
    assert psu.output_enabled is False
    assert disabled.output_enabled is False
    assert device.poller.output_enabled is False


def test_set_output_starts_the_timer_on_enable(psu, device):
    before = time.monotonic()
    enabled = tui_dashboard._set_output(_base_state(device), device, True)
    after = time.monotonic()
    assert enabled.enabled_at is not None
    assert before <= enabled.enabled_at <= after
    assert enabled.disabled_at is None


def test_set_output_freezes_the_timer_on_disable(psu, device):
    state = replace(_base_state(device), output_enabled=True, enabled_at=time.monotonic() - 5)
    disabled = tui_dashboard._set_output(state, device, False)
    assert disabled.disabled_at is not None
    assert disabled.enabled_at == state.enabled_at  # unchanged -- anchors the frozen duration


def test_set_output_resets_headroom_on_enable(psu, device):
    device.poller.peak_voltage = 9.0
    device.poller.avg_voltage = 5.0
    state = replace(_base_state(device), peak_voltage=9.0, avg_voltage=5.0)
    enabled = tui_dashboard._set_output(state, device, True)
    assert enabled.peak_voltage == 0.0
    assert enabled.avg_voltage == 0.0
    assert device.poller.peak_voltage == 0.0


def test_set_output_reports_communication_failure(psu, device, fake_transports):
    fake_transports[0].fail_writes = True
    new_state = tui_dashboard._set_output(_base_state(device), device, True)
    assert psu.output_enabled is False
    assert "simulated write failure" in new_state.status


# ---- Key dispatch --------------------------------------------------------


def test_handle_key_selection_wraps_and_clears_status(device):
    state = replace(_base_state(device), status="stale")
    up = tui_dashboard._handle_key(state, device, curses.KEY_UP, None)
    assert up.selected == len(tui_dashboard.FIELDS) - 1
    assert up.status == ""
    down = tui_dashboard._handle_key(up, device, curses.KEY_DOWN, None)
    assert down.selected == 0


def test_handle_key_left_right_change_the_step_place(device):
    state = _base_state(device)  # place_index 2 -> voltage step 0.1
    coarser = tui_dashboard._handle_key(state, device, curses.KEY_LEFT, None)
    assert coarser.place_index == 1  # -> step 1.0
    finer = tui_dashboard._handle_key(coarser, device, curses.KEY_RIGHT, None)
    assert finer.place_index == 2  # back to 0.1


def test_handle_key_left_right_clamp_at_the_ends(device):
    state = replace(_base_state(device), place_index=0)
    still_zero = tui_dashboard._handle_key(state, device, curses.KEY_LEFT, None)
    assert still_zero.place_index == 0
    last = len(tui_dashboard.FIELDS[0].places) - 1
    state = replace(_base_state(device), place_index=last)
    still_last = tui_dashboard._handle_key(state, device, curses.KEY_RIGHT, None)
    assert still_last.place_index == last


def test_handle_key_plus_minus_step_by_the_current_place(psu, device):
    state = replace(_base_state(device), place_index=1)  # voltage step 1.0
    up = tui_dashboard._handle_key(state, device, ord("+"), None)
    assert up.values["voltage"] == pytest.approx(6.0)
    down = tui_dashboard._handle_key(up, device, ord("-"), None)
    assert down.values["voltage"] == pytest.approx(5.0)


def test_handle_key_space_toggles_output(psu, device):
    state = _base_state(device)
    enabled = tui_dashboard._handle_key(state, device, ord(" "), None)
    assert enabled.output_enabled is True
    assert psu.output_enabled is True
    disabled = tui_dashboard._handle_key(enabled, device, ord(" "), None)
    assert disabled.output_enabled is False
    assert psu.output_enabled is False


def test_handle_key_ignores_unrecognized_keys(device):
    state = _base_state(device)
    assert tui_dashboard._handle_key(state, device, ord("z"), None) == state
    assert tui_dashboard._handle_key(state, device, ord("r"), None) == state  # decommissioned


def test_init_colors_falls_back_without_a_real_terminal():
    styles = tui_dashboard._init_colors()
    assert styles[tui_dashboard.STYLE_NORMAL] == curses.A_NORMAL
    assert styles[tui_dashboard.STYLE_ENABLED] == curses.A_BOLD
    assert styles[tui_dashboard.STYLE_TRIPPED] == curses.A_BOLD | curses.A_REVERSE
    assert styles[tui_dashboard.STYLE_LIVE_BAR] == curses.A_REVERSE
    assert styles[tui_dashboard.STYLE_SELECTED_ROW] == curses.A_REVERSE


# ---- Main loop integration -------------------------------------------------


def test_main_loop_steps_enables_and_quits_with_confirmed_disable(monkeypatch, fake_transports):
    monkeypatch.setattr(tui_dashboard.time, "sleep", lambda seconds: None)
    screen = FakeScreen([ord("+"), ord(" "), ord("q"), ord("y")])

    tui_dashboard.main(screen)

    transport = fake_transports[0]
    assert transport.closed is True
    assert transport.registers[0x0030] == 510  # voltage stepped 5.00 -> 5.10
    assert transport.registers[0x0001] == 0  # enabled, then confirmed off before quit


def test_main_loop_survives_a_communication_error_without_crashing(monkeypatch):
    created = []

    def factory(port, baudrate=9600, slave=1, timeout=1.0):
        transport = FlakyAfterConnectTransport(
            port, baudrate=baudrate, slave=slave, timeout=timeout
        )
        created.append(transport)
        return transport

    monkeypatch.setattr(hm310t.client, "Transport", factory)
    monkeypatch.setattr(tui_dashboard.time, "sleep", lambda seconds: None)
    screen = FakeScreen([ord("q")])

    tui_dashboard.main(screen)  # must not raise

    assert created[0].closed is True

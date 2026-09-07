"""A curses control panel for a live HM310T (ported from the old psui.py).

CAUTION: Space toggles the output. Enabling it ENERGIZES the output -- the
HM310T sources up to 10 A / 300 W. Run only with nothing (or a known-safe
load) on the terminals. This panel does NOT force OVP/OCP/OPP to conservative
values at startup -- it reads whatever the device already has and lets you
edit any of the five setpoints before enabling.

All five setpoints, the live reading, and protection status are polled
continuously in the background, so a change made from the device's own front
panel shows up here too, not just changes made through this panel.

Visual design follows one rule: visual weight is spent almost entirely on the
two states that are rare and consequential -- output live, and protection
tripped. Everything else (setpoint values, step size, headroom bars) stays
visually quiet by default, specifically so it never competes with those two.

    - Output live: a solid full-width yellow bar with a live-counting timer.
      This is this script's own clock, not read from the device -- a hardware
      sweep confirmed there's no such Modbus register. Freezes on disable,
      resets on the next enable (including one triggered from the front panel).
    - Protection tripped: names exactly what tripped, bold red, on its own line.
    - Selected setpoint: the row is reverse-video highlighted, and within it,
      the single digit the current step size targets is left un-reversed --
      reverse-on-reverse reads as plain, so that one digit stands out precisely
      because it ISN'T highlighted like the rest of the row.
    - Headroom: live voltage/current plotted as a bar against OVP/OCP, with a
      peak marker (bold yellow, resets on enable like the on-time counter) and
      a running-average marker (dim, cumulative mean since the last enable).

    python examples/tui_dashboard.py          # uses /dev/ttyUSB0
"""

from __future__ import annotations

import curses
import locale
import math
import threading
import time
from dataclasses import dataclass, replace

from hm310t import (
    HM310TError,
    Measurement,
    PowerSupply,
    PowerSupplyCommunicationError,
    ProtectionStatus,
)


@dataclass(frozen=True)
class Field:
    key: str  # PowerSupply attribute name
    label: str
    unit: str
    places: tuple[float, ...]  # step sizes, coarsest to finest; Left/Right cycle through them
    decimals: int  # display precision; the library handles real register precision


POLL_INTERVAL = 0.3  # seconds between live setpoint/measurement/protection/output reads
TICK_DELAY = 0.03  # seconds between input checks -- keeps keys responsive
BAR_WIDTH = 20  # characters between the [brackets] of a headroom bar

FIELDS = (
    Field("voltage", "Voltage", "V", places=(10.0, 1.0, 0.1, 0.01), decimals=2),
    Field("current", "Current", "A", places=(1.0, 0.1, 0.01, 0.001), decimals=3),
    Field("ovp", "OVP", "V", places=(10.0, 1.0, 0.1, 0.01), decimals=2),
    Field("ocp", "OCP", "A", places=(1.0, 0.1, 0.01, 0.001), decimals=3),
    Field("opp", "OPP", "W", places=(100.0, 10.0, 1.0, 0.1), decimals=1),
)
assert len({len(field.places) for field in FIELDS}) == 1, "place_index is shared across fields"

STYLE_NORMAL = "normal"
STYLE_ENABLED = "enabled"  # yellow accent -- ties the peak tick back to "happened while live"
STYLE_TRIPPED = "tripped"
STYLE_LIVE_BAR = "live_bar"  # solid full-row fill for the output-on banner
STYLE_SELECTED_ROW = "selected_row"

BOLT = "⚡"  # HIGH VOLTAGE SIGN

LEFT_COL = 2
RIGHT_COL = 42
HEADER_HEIGHT = 4  # title, blank, output-state line, blank -- see _render's header section
PROMPT_ROW = HEADER_HEIGHT + 1 + len(FIELDS)  # directly under the setpoints list
# Right column is much taller than the setpoints list (headroom bars), so PROMPT_ROW
# falls within its vertical span. Bounding the prompt's width keeps it clear of that
# column instead of blanking whatever it's showing on the same row.
PROMPT_WIDTH = RIGHT_COL - LEFT_COL - 1

# A single (text, style) segment; a Line is several concatenated left-to-right --
# needed so one row can mix styles (e.g. a reversed row with one un-reversed digit).
Segment = tuple[str, str]
Line = list[Segment]


@dataclass
class PanelState:
    """Everything needed to render one frame.

    ``values``/``measurement``/``protection``/``output_enabled``/``peak_*``/
    ``avg_*`` all mirror the background Poller (see below) -- none of them are
    locally-owned caches, since all of them can change on their own (a
    front-panel edit, a trip, another Modbus client). ``enabled_at``/
    ``disabled_at`` are this script's own clock for the on-time counter; the
    device has no such register.
    """

    selected: int
    place_index: int
    status: str
    values: dict[str, float]
    measurement: Measurement
    protection: ProtectionStatus
    output_enabled: bool
    enabled_at: float | None
    disabled_at: float | None
    peak_voltage: float
    peak_current: float
    avg_voltage: float
    avg_current: float


class Poller:
    """Keeps setpoints/measurement/protection/output fresh on a background thread.

    A single Modbus RTU exchange over USB-serial can take long enough (turnaround
    time, plus whatever a passthrough layer like WSL2 adds) that doing it inline
    in the input loop makes every keypress -- including ones like the arrow keys
    that never touch the device -- wait behind it. Running it here instead means
    the input loop only ever reads already-fetched values, never the device
    itself. `lock` is shared with the main thread's key handling: the Modbus
    link is half-duplex and two overlapping requests would corrupt both, and
    output_enabled/values are written from BOTH sides (the poll here, a user's
    edit there), so those read-then-store/write-then-store pairs must be
    mutually exclusive, not just the raw device access.

    Also tracks peak/running-average voltage and current while output is on,
    for the headroom bars -- sampled once per poll cycle here (a clean, evenly
    spaced series), not in the input loop's much faster tick.
    """

    def __init__(self, psu: PowerSupply, lock: threading.Lock) -> None:
        self._psu = psu
        self._lock = lock
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.values = {field.key: 0.0 for field in FIELDS}
        self.measurement = Measurement(0.0, 0.0, 0.0)
        self.protection = ProtectionStatus(False, False, False, False, False)
        self.output_enabled = False
        self.error: str | None = None
        self.peak_voltage = 0.0
        self.peak_current = 0.0
        self.avg_voltage = 0.0
        self.avg_current = 0.0
        self._voltage_sum = 0.0
        self._current_sum = 0.0
        self._sample_count = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def reset_headroom(self) -> None:
        """Call under `lock` at the moment output transitions off->on: peak and
        running average both describe the CURRENT on-period only."""
        self.peak_voltage = 0.0
        self.peak_current = 0.0
        self.avg_voltage = 0.0
        self.avg_current = 0.0
        self._voltage_sum = 0.0
        self._current_sum = 0.0
        self._sample_count = 0

    def read_once(self) -> None:
        """One synchronous read cycle -- the initial seed before the background
        thread starts, and the thread's own repeated cycle below."""
        with self._lock:
            self.values = {field.key: getattr(self._psu, field.key) for field in FIELDS}
            self.measurement = self._psu.read_measurement()
            self.protection = self._psu.read_protection_status()
            self.output_enabled = self._psu.output_enabled
            if self.output_enabled:
                self.peak_voltage = max(self.peak_voltage, self.measurement.voltage)
                self.peak_current = max(self.peak_current, self.measurement.current)
                self._sample_count += 1
                self._voltage_sum += self.measurement.voltage
                self._current_sum += self.measurement.current
                self.avg_voltage = self._voltage_sum / self._sample_count
                self.avg_current = self._current_sum / self._sample_count

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.read_once()
                self.error = None
            except PowerSupplyCommunicationError as exc:
                self.error = str(exc)
            # wait() (not sleep()) so stop() interrupts a pending wait immediately,
            # and it times the gap from when THIS read finished, not when it started
            # -- a slow read can't compress the rest of the interval away.
            self._stop.wait(POLL_INTERVAL)


@dataclass(frozen=True)
class Device:
    """Bundles what key handling needs to safely touch the physical device."""

    psu: PowerSupply
    lock: threading.Lock
    poller: Poller


def _fmt(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _fmt_duration(seconds: float) -> str:
    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _elapsed(state: PanelState, now: float) -> float | None:
    """Seconds the output has been (or was last) on, or None if never enabled
    this session. Counts up live while enabled; frozen at the last duration
    once disabled, until the next enable resets it."""
    if state.enabled_at is None:
        return None
    if state.output_enabled:
        return now - state.enabled_at
    if state.disabled_at is not None:
        return state.disabled_at - state.enabled_at
    return None


def _initial_enabled_at(poller: Poller, now: float) -> float | None:
    """Seeds the on-time counter at startup. If output is already on when this
    panel connects (left on from a prior session, or the front panel), there's
    no way to know when it actually turned on, so the counter starts from now.
    Without this, the counter would never start at all: output_enabled already
    reads True on the very first tick, so the off->on EDGE that normally
    triggers it (see main()'s loop) would never fire."""
    return now if poller.output_enabled else None


def _protection_summary(protection: ProtectionStatus) -> str:
    if not protection.tripped:
        return "OK"
    tripped = [
        name
        for name, is_tripped in (
            ("OVP", protection.is_ovp),
            ("OCP", protection.is_ocp),
            ("OPP", protection.is_opp),
            ("OTP", protection.is_otp),
            ("SCP", protection.is_scp),
        )
        if is_tripped
    ]
    return "TRIPPED: " + ", ".join(tripped)


def _status_style(status: str) -> str:
    return STYLE_TRIPPED if status.startswith("Communication error") else STYLE_NORMAL


def _split_target_digit(padded_value: str, place: float) -> list[tuple[str, bool]]:
    """Splits a right-aligned, already-formatted number into (text, is_target)
    segments, isolating the single digit `place` (a power-of-ten step size)
    refers to -- e.g. padded_value='  6.00', place=0.1 isolates the tenths
    digit. Falls back to one unmarked segment if that digit doesn't exist
    (e.g. asking for a tens digit on a single-digit value)."""
    if "." not in padded_value:
        return [(padded_value, False)]
    power = round(math.log10(place))
    dot_index = padded_value.index(".")
    target_index = dot_index - power if power < 0 else dot_index - 1 - power
    if not (0 <= target_index < len(padded_value)) or not padded_value[target_index].isdigit():
        return [(padded_value, False)]
    return [
        (padded_value[:target_index], False),
        (padded_value[target_index], True),
        (padded_value[target_index + 1 :], False),
    ]


def _bar_ratio(value: float, limit: float) -> float:
    return 0.0 if limit <= 0 else min(max(value / limit, 0.0), 1.0)


def _bar_text(value: float, limit: float) -> str:
    filled = round(_bar_ratio(value, limit) * BAR_WIDTH)
    return "[" + "▓" * filled + "░" * (BAR_WIDTH - filled) + "]"


def _tick_line(peak: float, avg: float, limit: float) -> Line:
    """A row of blank cells aligned under a bar's [brackets], with a dim '·' at
    the average position and a bold yellow '▲' at the peak position (drawn
    after the average, so it wins if they land on the same cell -- peak is
    always >= average in value, so it's never LEFT of the average tick)."""
    avg_pos = 1 + min(int(_bar_ratio(avg, limit) * BAR_WIDTH), BAR_WIDTH - 1)
    peak_pos = 1 + min(int(_bar_ratio(peak, limit) * BAR_WIDTH), BAR_WIDTH - 1)
    cells = [" "] * (BAR_WIDTH + 2)
    cells[avg_pos] = "·"
    cells[peak_pos] = "▲"
    before = "".join(cells[:peak_pos])
    after = "".join(cells[peak_pos + 1 :])
    return [(before, STYLE_NORMAL), (cells[peak_pos], STYLE_ENABLED), (after, STYLE_NORMAL)]


def _headroom_block(
    label: str, live: float, limit: float, peak: float, avg: float, unit: str, decimals: int
) -> list[Line]:
    percent = round(_bar_ratio(live, limit) * 100)
    peak_pct = round(_bar_ratio(peak, limit) * 100)
    avg_pct = round(_bar_ratio(avg, limit) * 100)
    return [
        [(f"{label}  {percent}%", STYLE_NORMAL)],
        [(_bar_text(live, limit), STYLE_NORMAL)],
        _tick_line(peak, avg, limit),
        [
            (
                f"  peak {_fmt(peak, decimals)} {unit} ({peak_pct}%)   "
                f"avg {_fmt(avg, decimals)} {unit} ({avg_pct}%)",
                STYLE_NORMAL,
            )
        ],
    ]


def _setpoint_line(field: Field, state: PanelState, selected: bool) -> Line:
    value_text = f"{_fmt(state.values[field.key], field.decimals):>9}"
    if not selected:
        cursor = "  "
        return [(f"{cursor}{field.label:<8} {value_text} {field.unit}", STYLE_NORMAL)]

    row_style = STYLE_SELECTED_ROW
    prefix = f"▸ {field.label:<8} "
    place = field.places[state.place_index]
    line: Line = [(prefix, row_style)]
    for text, is_target in _split_target_digit(value_text, place):
        if text:
            line.append((text, STYLE_NORMAL if is_target else row_style))
    line.append((f" {field.unit}  step {_fmt(place, field.decimals)}", row_style))
    return line


def _render(state: PanelState, now: float, width: int) -> dict[str, list[Line]]:
    """Pure function: state + a clock reading + terminal width -> a structured
    layout. _draw below positions the sections on screen; kept separate so
    this stays testable without curses."""
    duration = _elapsed(state, now)
    header: list[Line] = [[("HM310T Control Panel", STYLE_NORMAL)], [("", STYLE_NORMAL)]]
    if state.output_enabled:
        left_text = f"{BOLT} OUTPUT ON"
        right_text = _fmt_duration(duration or 0.0)
        pad = max(width - len(left_text) - len(right_text), 1)
        header.append([(f"{left_text}{' ' * pad}{right_text}", STYLE_LIVE_BAR)])
    elif duration is not None:
        header.append([(f"Output: OFF   (last run {_fmt_duration(duration)})", STYLE_NORMAL)])
    else:
        header.append([("Output: OFF", STYLE_NORMAL)])
    header.append([("", STYLE_NORMAL)])

    left: list[Line] = [[("SETPOINTS", STYLE_NORMAL)]]
    for i, field in enumerate(FIELDS):
        left.append(_setpoint_line(field, state, selected=(i == state.selected)))

    right: list[Line] = [
        [("LIVE READING", STYLE_NORMAL)],
        [
            (
                f"{state.measurement.voltage:>7.2f} V "
                f"{state.measurement.current:>8.3f} A "
                f"{state.measurement.power:>8.3f} W",
                STYLE_NORMAL,
            )
        ],
        [("", STYLE_NORMAL)],
    ]
    right += _headroom_block(
        "V/OVP",
        state.measurement.voltage,
        state.values["ovp"],
        state.peak_voltage,
        state.avg_voltage,
        "V",
        2,
    )
    right.append([("", STYLE_NORMAL)])
    right += _headroom_block(
        "A/OCP",
        state.measurement.current,
        state.values["ocp"],
        state.peak_current,
        state.avg_current,
        "A",
        3,
    )
    right.append([("", STYLE_NORMAL)])
    right.append([("PROTECTION", STYLE_NORMAL)])
    right.append(
        [
            (
                _protection_summary(state.protection),
                STYLE_TRIPPED if state.protection.tripped else STYLE_NORMAL,
            )
        ]
    )

    footer: list[Line] = [
        [("", STYLE_NORMAL)],
        [(state.status, _status_style(state.status))],
        [("", STYLE_NORMAL)],
        [("Up/Down j/k select field    Left/Right h/l step size    +/- adjust", STYLE_NORMAL)],
        [("Enter exact value    Space toggle output    q quit", STYLE_NORMAL)],
    ]
    return {"header": header, "left": left, "right": right, "footer": footer}


def _init_colors() -> dict[str, int]:
    """Maps style names to curses attributes.

    Falls back to bold/reverse-only if the terminal has no color support, or
    (as in tests) curses was never actually initialized via initscr().
    """
    try:
        curses.start_color()
        curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        return {
            STYLE_NORMAL: curses.A_NORMAL,
            STYLE_ENABLED: curses.color_pair(1) | curses.A_BOLD,
            STYLE_TRIPPED: curses.color_pair(2) | curses.A_BOLD,
            # No A_BOLD here: many terminals render bold-black as gray (there's no
            # darker-than-black "bright" variant), which washes out the contrast
            # against the yellow background -- plain black reads much darker.
            STYLE_LIVE_BAR: curses.color_pair(3),
            STYLE_SELECTED_ROW: curses.A_REVERSE,
        }
    except curses.error:
        return {
            STYLE_NORMAL: curses.A_NORMAL,
            STYLE_ENABLED: curses.A_BOLD,
            STYLE_TRIPPED: curses.A_BOLD | curses.A_REVERSE,
            STYLE_LIVE_BAR: curses.A_REVERSE,
            STYLE_SELECTED_ROW: curses.A_REVERSE,
        }


def _safe_addstr(
    stdscr: curses.window, row: int, col: int, text: str, attr: int = curses.A_NORMAL
) -> None:
    try:
        stdscr.addstr(row, col, text, attr)
    except (curses.error, UnicodeError):
        pass  # terminal too small, or can't encode this line -- clip rather than crash


def _draw_line(
    stdscr: curses.window, row: int, col: int, line: Line, styles: dict[str, int]
) -> None:
    x = col
    for text, style in line:
        if text:
            _safe_addstr(stdscr, row, x, text, styles.get(style, curses.A_NORMAL))
        x += len(text)


def _draw(stdscr: curses.window, state: PanelState, styles: dict[str, int], now: float) -> None:
    stdscr.erase()
    # -1: writing all the way to the terminal's last column can trigger an
    # implicit wrap in curses (writes into the next row instead of just stopping).
    width = stdscr.getmaxyx()[1] - 1
    layout = _render(state, now, width)

    row = 0
    for line in layout["header"]:
        _draw_line(stdscr, row, 0, line, styles)
        row += 1

    body_top = row
    for i, line in enumerate(layout["left"]):
        _draw_line(stdscr, body_top + i, LEFT_COL, line, styles)
    for i, line in enumerate(layout["right"]):
        _draw_line(stdscr, body_top + i, RIGHT_COL, line, styles)

    row = body_top + max(len(layout["left"]), len(layout["right"]))
    for line in layout["footer"]:
        _draw_line(stdscr, row, 0, line, styles)
        row += 1

    stdscr.refresh()


def _prompt(stdscr: curses.window, prompt: str, row: int, col: int, width: int) -> str | None:
    """Blocking-read a line of text at (row, col), touching only `width` columns --
    NOT the rest of the row -- so it doesn't blank out whatever else is drawn
    there (e.g. the LIVE READING column). None means the user hit Esc."""
    text = ""
    stdscr.nodelay(False)
    try:
        while True:
            _safe_addstr(stdscr, row, col, " " * width)
            _safe_addstr(stdscr, row, col, f"{prompt}{text}"[:width])
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (10, 13, curses.KEY_ENTER):
                return text
            if ch == 27:  # Esc
                return None
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                text = text[:-1]
            elif 32 <= ch < 127:
                text += chr(ch)
    finally:
        stdscr.nodelay(True)


def _apply(state: PanelState, field: Field, device: Device, target: float) -> PanelState:
    try:
        with device.lock:
            setattr(device.psu, field.key, target)
            # Mirror into the poller's copy in the SAME critical section as the
            # write, not after -- otherwise a poll already in flight (which read
            # the OLD value before this write) could land after this and clobber
            # it back to stale until the next poll cycle catches up.
            device.poller.values[field.key] = target
    except (HM310TError, ValueError) as exc:
        return replace(state, status=str(exc))
    values = dict(state.values)
    values[field.key] = target
    return replace(
        state,
        values=values,
        status=f"{field.label} set to {_fmt(target, field.decimals)} {field.unit}",
    )


def _step(state: PanelState, field: Field, device: Device, delta: float) -> PanelState:
    target = round(state.values[field.key] + delta, field.decimals)
    return _apply(state, field, device, target)


def _enter_value(
    state: PanelState, field: Field, device: Device, stdscr: curses.window
) -> PanelState:
    current = _fmt(state.values[field.key], field.decimals)
    # Two lines, both bounded to the setpoints column's width: a static context
    # line, then the input line below it. One long line ran past the setpoints
    # column and into LIVE READING's space.
    context = f"{field.label} ({field.unit}), currently {current}"
    _safe_addstr(stdscr, PROMPT_ROW, LEFT_COL, context[:PROMPT_WIDTH])
    stdscr.refresh()
    text = _prompt(
        stdscr,
        "New value (Esc cancels): ",
        PROMPT_ROW + 1,
        LEFT_COL,
        PROMPT_WIDTH,
    )
    if text is None:
        return replace(state, status="Cancelled")
    try:
        target = float(text)
    except ValueError:
        return replace(state, status=f"Not a number: {text!r}")
    return _apply(state, field, device, target)


def _set_output(state: PanelState, device: Device, enabled: bool) -> PanelState:
    t0 = time.monotonic()
    try:
        with device.lock:
            device.psu.output_enabled = enabled
            device.poller.output_enabled = enabled
            if enabled:
                device.poller.reset_headroom()
    except HM310TError as exc:
        return replace(state, status=str(exc))
    t1 = time.monotonic()
    # We can't know the device's own internal delay between receiving this write
    # and its state actually changing -- but assuming it happened at the midpoint
    # of our measured round-trip (the same idea NTP uses for clock sync) roughly
    # halves the error versus just using t1. latency_ms is the measured round-trip,
    # surfaced so it's visible rather than a hidden assumption.
    changed_at = t0 + (t1 - t0) / 2
    latency_ms = (t1 - t0) * 1000
    if enabled:
        return replace(
            state,
            output_enabled=True,
            enabled_at=changed_at,
            disabled_at=None,
            peak_voltage=0.0,
            peak_current=0.0,
            avg_voltage=0.0,
            avg_current=0.0,
            status=f"Output enabled (measured link latency ~{latency_ms:.0f} ms)",
        )
    return replace(
        state,
        output_enabled=False,
        disabled_at=changed_at,
        status=f"Output disabled (measured link latency ~{latency_ms:.0f} ms)",
    )


def _handle_key(state: PanelState, device: Device, key: int, stdscr: curses.window) -> PanelState:
    field = FIELDS[state.selected]
    if key in (curses.KEY_UP, ord("k")):
        return replace(state, selected=(state.selected - 1) % len(FIELDS), status="")
    if key in (curses.KEY_DOWN, ord("j")):
        return replace(state, selected=(state.selected + 1) % len(FIELDS), status="")
    if key in (curses.KEY_LEFT, ord("h")):
        return replace(state, place_index=max(state.place_index - 1, 0), status="")
    if key in (curses.KEY_RIGHT, ord("l")):
        max_index = len(field.places) - 1
        return replace(state, place_index=min(state.place_index + 1, max_index), status="")
    if key in (ord("+"), ord("=")):
        return _step(state, field, device, field.places[state.place_index])
    if key == ord("-"):
        return _step(state, field, device, -field.places[state.place_index])
    if key in (10, 13, curses.KEY_ENTER):
        return _enter_value(state, field, device, stdscr)
    if key == ord(" "):  # a single, easy-to-find-blind toggle -- see module docstring
        return _set_output(state, device, not state.output_enabled)
    return state


def _maybe_disable_on_quit(stdscr: curses.window, device: Device, output_enabled: bool) -> None:
    # Uses the last-known state rather than a fresh read: quitting must never crash
    # on a comms blip, and output_enabled is kept current by the poller and by
    # _set_output above.
    if not output_enabled:
        return
    stdscr.nodelay(False)
    try:
        _safe_addstr(stdscr, 0, 0, "Output is ON. Disable it before quitting? (y/n): ")
        stdscr.refresh()
        ch = stdscr.getch()
    finally:
        stdscr.nodelay(True)
    if ch in (ord("y"), ord("Y")):
        try:
            with device.lock:
                device.psu.output_enabled = False
        except HM310TError:
            pass  # comms may already be down; the front panel is the last resort


def _connect(stdscr: curses.window) -> PowerSupply | None:
    """Retry-connect loop. Returns the supply, or None if the user pressed 'q'."""
    stdscr.addstr("Attempting to connect to the power supply...\n")
    stdscr.refresh()
    retry_count = 0
    while True:
        try:
            return PowerSupply(port="/dev/ttyUSB0", baudrate=9600)
        except PowerSupplyCommunicationError:
            retry_count += 1
            stdscr.clear()
            stdscr.addstr(f"\nCould not reach the power supply (attempt #{retry_count}).\n")
            stdscr.addstr("\nPress 'q' to quit; retrying otherwise...\n")
            stdscr.refresh()
            stdscr.nodelay(True)
            if stdscr.getch() == ord("q"):
                return None
            time.sleep(4)


def main(stdscr: curses.window) -> None:
    try:
        locale.setlocale(locale.LC_ALL, "")  # needed for the bolt glyph to render correctly
    except locale.Error:
        pass  # fall back to the default locale; the glyph may not render, nothing fatal

    psu = _connect(stdscr)
    if psu is None:
        return

    lock = threading.Lock()
    poller = Poller(psu, lock)
    device = Device(psu, lock, poller)
    poller_started = False
    try:
        stdscr.nodelay(True)  # non-blocking getch()
        styles = _init_colors()
        try:
            poller.read_once()
            status = (
                "Connected. Protection trip points shown below are whatever the device already had."
            )
        except HM310TError as exc:
            # A comms blip right after connecting shouldn't crash the panel -- the
            # background poller below retries automatically every cycle.
            status = f"Could not read initial state ({exc}). Retrying automatically."
        enabled_at = _initial_enabled_at(poller, time.monotonic())
        if enabled_at is not None:
            status = f"{status} Output was already on -- timer starts from now, not the true total."
        state = PanelState(
            selected=0,
            place_index=2,  # matches the old fixed defaults (0.1 V, 0.01 A, 1 W)
            status=status,
            values=poller.values,
            measurement=poller.measurement,
            protection=poller.protection,
            output_enabled=poller.output_enabled,
            enabled_at=enabled_at,
            disabled_at=None,
            peak_voltage=poller.peak_voltage,
            peak_current=poller.peak_current,
            avg_voltage=poller.avg_voltage,
            avg_current=poller.avg_current,
        )
        poller.start()
        poller_started = True
    except BaseException:
        # Initialization can block on serial I/O too. It needs the same fail-safe
        # teardown as the event loop, even though the poller may not have started.
        try:
            with lock:
                psu.output_enabled = False
        except Exception:
            pass
        finally:
            if poller_started:
                poller.stop()
            psu.close()
        raise

    try:
        while True:
            was_enabled = state.output_enabled
            state = replace(
                state,
                values=poller.values,
                measurement=poller.measurement,
                protection=poller.protection,
                output_enabled=poller.output_enabled,
                peak_voltage=poller.peak_voltage,
                peak_current=poller.peak_current,
                avg_voltage=poller.avg_voltage,
                avg_current=poller.avg_current,
            )
            if poller.error is not None:
                state = replace(state, status=f"Communication error: {poller.error}")
            elif state.output_enabled != was_enabled:
                # Output changed without going through _set_output below (the front
                # panel, or another Modbus client) -- _set_output already set a more
                # precise timestamp and reset headroom when WE trigger the change,
                # so this only fires for a change this panel didn't just make itself.
                now = time.monotonic()
                if state.output_enabled:
                    with lock:
                        poller.reset_headroom()
                    state = replace(
                        state,
                        enabled_at=now,
                        disabled_at=None,
                        peak_voltage=0.0,
                        peak_current=0.0,
                        avg_voltage=0.0,
                        avg_current=0.0,
                        status="Output enabled (detected externally -- front panel?)",
                    )
                else:
                    state = replace(
                        state,
                        disabled_at=now,
                        status="Output disabled (detected externally -- front panel?)",
                    )

            _draw(stdscr, state, styles, time.monotonic())

            key = stdscr.getch()
            if key == ord("q"):
                _maybe_disable_on_quit(stdscr, device, state.output_enabled)
                break
            if key != -1:
                state = _handle_key(state, device, key, stdscr)

            stdscr.nodelay(True)
            time.sleep(TICK_DELAY)
    except BaseException:
        # Abnormal exit (Ctrl-C, a comms error mid-loop): fail safe -- never leave
        # the output energized with no in-process way to disable it. The deliberate
        # 'q' quit path above is a normal return, so it keeps its leave-on choice.
        try:
            with lock:
                psu.output_enabled = False
        except Exception:
            pass  # comms may be dead; the device's front panel is the last resort
        raise
    finally:
        poller.stop()
        psu.close()


if __name__ == "__main__":
    curses.wrapper(main)

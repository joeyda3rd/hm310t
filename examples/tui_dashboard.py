"""A tiny curses dashboard for a live HM310T (ported from the old psui.py).

CAUTION: The 'e' key ENERGIZES the output. The HM310T sources up to 10 A / 300 W.
Run only with nothing (or a known-safe load) on the terminals. On quit, if the
output is on, the dashboard asks before leaving it running.

    python examples/tui_dashboard.py          # uses /dev/ttyUSB0
"""

from __future__ import annotations

import curses
import time

from hm310t import PowerSupply, PowerSupplyCommunicationError


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
    ps = _connect(stdscr)
    if ps is None:
        return

    stdscr.nodelay(True)  # non-blocking getch()
    try:
        # Conservative protection before the 'e' key can energize anything. This
        # demo sweeps VOLTAGE, so OVP sits at the device ceiling; OCP and OPP cap
        # the real thermal hazards (current, power) at low values.
        ps.ovp = 30.0
        ps.ocp = 1.0
        ps.opp = 30.0
        while True:
            m = ps.read_measurement()
            stdscr.clear()
            stdscr.addstr(f"Output enabled: {ps.output_enabled}\n")
            stdscr.addstr(f"Setpoint:  {ps.voltage} V  {ps.current} A\n")
            stdscr.addstr(f"Measured:  {m.voltage} V  {m.current} A  {m.power} W\n")
            stdscr.addstr("\nKeys: q quit | + / - voltage | e enable output | d disable output\n")

            c = stdscr.getch()
            if c == ord("q"):
                if ps.output_enabled:
                    stdscr.addstr("\nDisable the output before quitting? (y/n)\n")
                    stdscr.refresh()
                    stdscr.nodelay(False)
                    if stdscr.getch() == ord("y"):
                        ps.output_enabled = False
                break
            elif c == ord("+"):
                ps.voltage = min(ps.voltage + 1, ps.voltage_limit)
            elif c == ord("-"):
                ps.voltage = max(ps.voltage - 1, 0)
            elif c == ord("e"):
                ps.output_enabled = True
            elif c == ord("d"):
                ps.output_enabled = False

            stdscr.nodelay(True)
            time.sleep(0.1)
    except BaseException:
        # Abnormal exit (Ctrl-C, a comms error mid-loop): fail safe -- never leave
        # the output energized with no in-process way to disable it. The deliberate
        # 'q' quit path above is a normal return, so it keeps its leave-on choice.
        try:
            ps.output_enabled = False
        except Exception:
            pass  # comms may be dead; the device's front panel is the last resort
        raise
    finally:
        ps.close()


if __name__ == "__main__":
    curses.wrapper(main)

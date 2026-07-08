import curses
import time
from pyHM310T import PowerSupply, PowerSupplyCommunicationError

def main(stdscr):
    # Initialization prompt
    stdscr.addstr("Attempting to connect to the power supply...\n")
    stdscr.refresh()
    #curses.doupdate()
    
    # Loop for initializing the PowerSupply object
    retry_count = 0
    while True:
        try:
            # Initialize the power supply
            ps = PowerSupply(port='/dev/ttyUSB0', baudrate=9600)
            break  # If initialization is successful, break out of the loop
        except PowerSupplyCommunicationError:
            retry_count += 1
            stdscr.clear()
            stdscr.addstr(f"\nFailed to communicate with the power supply. Attempt #{retry_count}. Retrying...\n")
            stdscr.addstr("\nPress 'q' to quit.\n")
            stdscr.refresh()
            #curses.doupdate()
            stdscr.nodelay(True)  # Make getch() blocking
            if stdscr.getch() == ord('q'):
                return
            stdscr.nodelay(True)  # Make getch() non-blocking again
            time.sleep(4)
            stdscr.addstr("\nRetrying...\n")
            stdscr.refresh()
            #curses.doupdate()
            time.sleep(1)

            
    # Set up the screen
    stdscr.clear()
    stdscr.nodelay(True)  # Make getch() non-blocking

    while True:
        # Display the current status
        stdscr.clear()
        stdscr.addstr(f"Output enabled: {ps.is_output_enabled()}\n")
        stdscr.addstr(f"Voltage: {ps.get_voltage()}V\n")
        stdscr.addstr(f"Current: {ps.get_current()}A\n")
        stdscr.addstr(f"Output Voltage: {ps.get_voltage_display()}V\n")
        stdscr.addstr(f"Output Current: {ps.get_current_display()}A\n")
        stdscr.addstr(f"Output Power: {ps.get_power_display()}W\n")
        stdscr.addstr("\nPress 'q' to quit, '+' to increase voltage, '-' to decrease voltage, 'e' to enable output, 'd' to disable output.\n")

        # Handle key presses
        c = stdscr.getch()
        if c == ord('q'):
            if ps.is_output_enabled():
                stdscr.addstr("\nDo you want to disable the power output before quitting? (y/n)\n")
                stdscr.refresh()
                stdscr.nodelay(False)  # Make getch() blocking
                c = stdscr.getch()
                if c == ord('y'):
                    ps.disable_output()
            break
        elif c == ord('+'):
            ps.set_voltage(min(ps.get_voltage() + 1, ps.voltage_limit))
        elif c == ord('-'):
            ps.set_voltage(max(ps.get_voltage() - 1, 0))
        elif c == ord('e'):
            if not ps.is_output_enabled():
                ps.enable_output()
                stdscr.addstr("\nPower output enabled.\n")
            else:
                stdscr.addstr("\nPower output is already enabled.\n")
        elif c == ord('d'):
            if ps.is_output_enabled():
                ps.disable_output()
                stdscr.addstr("\nPower output disabled.\n")
            else:
                stdscr.addstr("\nPower output is already disabled.\n")
         
        stdscr.nodelay(True)  # Make getch() non-blocking again
    

if __name__ == "__main__":
    curses.wrapper(main)



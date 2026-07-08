from pyHM310T import PowerSupply

# Create instance with default parameters
# COM port, baudrate = 9600, slave=1, voltage_limit=30.0, current_limit=10.0):
power_supply = PowerSupply(port='/dev/ttyUSB0')

# Alternatively, create instance with custom parameters
# power_supply = PowerSupply('COM4', 115200, 2, 10.0, 5.0)

# Set the voltage to 5V
power_supply.set_voltage(0)

# Enable the output
power_supply.enable_output()

# Check if output is enabled
if power_supply.is_output_enabled():
    print("Output is enabled")

# Set the voltage to 5V
power_supply.set_voltage(5.0)

# Get the set voltage
set_voltage = power_supply.get_voltage()
print(f"Set voltage: {set_voltage}V")

# Set the current to 1A
power_supply.set_current(0.05)

# Get the set current
set_current = power_supply.get_current()
print(f"Set current: {set_current}A")

# Get voltage, current and power display (requires a load present)
print(f"Voltage display: {power_supply.get_voltage_display()}V")
print(f"Current display: {power_supply.get_current_display()}A")
print(f"Power display: {power_supply.get_power_display()}W")

# Get and set communication address
print(f"Communication address: {power_supply.get_comm_address()}")

# Get and set Over Voltage Protection (OVP) status
print(f"OVP status: {power_supply.get_ovp()}")
power_supply.set_ovp(10)
print(f"New OVP status: {power_supply.get_ovp()}")

# Get and set Over Current Protection (OCP) status
print(f"OCP status: {power_supply.get_ocp()}")
power_supply.set_ocp(2)
print(f"New OCP status: {power_supply.get_ocp()}")

# Get and set Over Power Protection (OPP) status
print(f"OPP status: {power_supply.get_opp()}")
power_supply.set_opp(20)
print(f"New OPP status: {power_supply.get_opp()}")

# Get protection status
print(f"Protection status: {power_supply.get_protection_status()}")

#disable power output
power_supply.disable_output()

# Check if output is disabled
if not(power_supply.is_output_enabled()):
    print("Output is disabled")

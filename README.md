# Hanmatek Modbus Power Supply Python Library

This repository contains a Python library to interact with the Hanmatek HM310T power supply over the Modbus interface.  
Learn how this is accomplished for interacting with similar devices below in [#further reading](#further-reading).  

<img src="/OEM-docs/61osnNY3qPL._SL1500_.jpg?raw=true" width="250"> <img src="/OEM-docs/81EDT-klVJL._SL1500_.jpg?raw=true" width="250">

⚠️ **Safety Warning**

The Hanmatek HM310T power supply is a device that can produce potentially dangerous levels of voltage and current. Always follow safety guidelines when working with electricity. Ensure your device is properly grounded and do not work on live circuits. 

This software is provided "as is", without warranty of any kind, express or implied. Incorrect use of this software could lead to damage to your power supply or other equipment, or personal injury. Use this software responsibly and at your own risk.

⚠️ **Use At Your Own Risk**

By using this software, you agree that the authors and maintainers of this software are not liable for any damage to equipment, or any personal injury, that may occur through normal or abnormal use of this software. Always double-check your work and never leave a powered device unattended.

## Requirements

- Python 3.7 or higher
- PyModbus (version 3.2.2 was used for development)
- A Hanmatek HM310T power supply connected to a PC by USB
- May work with other Hanmatek or Modbus enabled power supplies, requires you to reverse engineer the unit. See [further reading](#further-reading) below for technical details and register values.



...

## Installation

To install the library, clone this repository and install it using pip:

```bash
pip install -v "pymodbus==3.2.2"
pip install pyserial
git clone https://github.com/joeyda3rd/hanmatek-power-supply.git
cd hanmatek-power-supply
pip install .
```

## Usage

### Simple Application Example
See the simple CLI application example (psui.py)  
<img src="/images/screenshot-psui.jpg?raw=true" width="500">

Here are usage examples:

```python
from pyHM310T import PowerSupply

# Create instance with default parameters
# COM port, baudrate = 9600, slave=1, voltage_limit=30.0, current_limit=10.0):
power_supply = PowerSupply(port='/dev/ttyUSB0')

# Alternatively, create instance with custom parameters
# power_supply = PowerSupply('COM4', 115200, 2, 10.0, 5.0)

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
power_supply.set_current(1.0)

# Get the set current
set_current = power_supply.get_current()
print(f"Set current: {set_current}A")

# Get voltage, current and power display (requires a load present)
print(f"Voltage display: {power_supply.get_voltage_display()}V")
print(f"Current display: {power_supply.get_current_display()}A")
print(f"Power display: {power_supply.get_power_display()}W")

# Get and set communication address
print(f"Communication address: {power_supply.get_comm_address()}")
# uncomment to change address, but will require new connection at new address.
# power_supply.set_comm_address(2)
# print(f"New communication address: {power_supply.get_comm_address()}")

# Get protection status
print(f"Protection status: {power_supply.get_protection_status()}")

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

#disable power output
power_supply.disable_output()

# Check if output is disabled
if not(power_supply.is_output_enabled()):
    print("Output is disabled")

```

### Methods

Here are the methods provided by the `PowerSupply` class:

- `enable_output(enable=True)`: Enable or disable the power output. `enable` should be a boolean value.
- `is_output_enabled()`: Check if the power output is enabled. Returns a boolean value.
- `disable_output()`: Disable the power output.
- `set_voltage(voltage)`: Set the output voltage. `voltage` should be a float value between 0 and 30 (or set limit).
- `get_voltage()`: Get the set output voltage. Returns a float value.
- `set_current(current)`: Set the output current. `current` should be a float value between 0 and 10 (or set limit).
- `get_current()`: Get the set output current. Returns a float value.
- `get_voltage_display()`: Get the displayed output voltage. Returns a float value.
- `get_current_display()`: Get the displayed output current. Returns a float value.
- `get_power_display()`: Get the displayed output power. Returns a float value.
- `get_comm_address()`: Get the communication address. Returns an integer value between 1 and 250.
- `set_comm_address(address)`: Set the communication address. `address` should be an integer value between 1 and 250.
- `get_protection_status()`: Get the protection status. Returns a dictionary with the keys 'isOVP', 'isOCP', 'isOPP', 'isOTP', and 'isSCP'.
- `get_ovp()`, `set_ovp(ovp)`: Get or set the Over Voltage Protection (OVP) value. `ovp` should be a float value between 0 and 30.
- `get_ocp()`, `set_ocp(ocp)`: Get or set the Over Current Protection (OCP) value. `ocp` should be a float value between 0 and 10.
- `get_opp()`, `set_opp(opp)`: Get or set the Over Power Protection (OPP) value. `opp` should be a float value between 0 and 300.


## Contributing

Contributions are welcome! Please open an issue if you encounter a bug or have a feature request. If you want to contribute code, please open a pull request.

## License

This library is licensed under the MIT license.

---
## Further Reading

When reverse engineering a power supply with a modbus interface, either over serial or other communication protocol, it's going to be essential to know the register addresses for the various I/O and the function code. In this case, we got lucky and the OEM provided that documentation. 
It's possible to learn these by using a script to brute force read and write (and read) each address from 1 to 9999 (see modbus_read.py in code) and/or sniffing the unencrypted traffic of OEM software. It's important to understand the Modbus protocol register addressing. 

In the Modbus protocol, there are four types of data that can be accessed, each with its own address space:

1. Coils (also known as Discrete Outputs): Addresses 00001 to 09999
2. Discrete Inputs: Addresses 10001 to 19999
3. Input Registers: Addresses 30001 to 39999
4. Holding Registers: Addresses 40001 to 49999

Each of these address spaces can contain up to 10,000 addresses, for a total of 40,000 addresses. However, not all devices will use all of these addresses. The actual number of addresses used will depend on the specific device and its configuration.

It's also worth noting that in the Modbus protocol, addresses are often represented in a zero-based format. For example, the first holding register is often referred to as register 40001 in documentation, but in the actual Modbus messages, it would be referred to as holding register 0.

In our case the entirety of the registers we accessed were in the holding registers space. The use of holding registers is common in Modbus devices, including power supplies, because holding registers can be read from and written to, making them versatile for various types of data. However, it's not guaranteed that every Modbus power supply will only use holding registers.

The specific Modbus registers used, and their purpose, can vary widely between different devices and manufacturers. Some devices might use input registers to provide read-only data, or coils and discrete inputs for binary data.

The best source of information about which registers are used by a particular device is the device's Modbus map or register map, which is usually provided in the device's documentation or manual. This map will list all the Modbus addresses used by the device, along with a description of the data stored at each address.

It's important to know what programming protocol and communication protocol are being used with your device as there are others besides Modbus or serial. 

[Documentation provided by the OEM](OEM-docs/Modbus.pdf) (This was included on a CD provided by OEM)

The registers will accept read (03) and write (06) instructions.

Registers from documentation
| Number | Function | Type | Decimal Places Capacity | Read/Write | Register Address |
| ------ | -------- | ---- | ----------------------- | ---------- | ---------------- |
| 0 | Output On/Off | Boolean | 0 | r,w | 0x0001 |
| 1 | Protect Status | Struct | 0 | r | 0x0002 |
| 2 | Specification | unsigned short | 0 | r | 0x0003 |
| 3 | Tail Classification | hexadecimal | 0 | r | 0x0004 |
| 4 | Decimal Point Values | hexadecimal | 0 | r | 0x0005 |
| 5 | Voltage Display Value | unsigned short | 2 | r | 0x0010 |
| 6 | Current Display Value | unsigned short | 3 | r | 0x0011 |
| 7 | Power Display Value | 2 integers? | 3 | r | 0x0012,0x0013 |
| 9 | Set Voltage | unsigned short | 2 | r,w | 0x0030 |
| 10 | Set Current | unsigned short | 3 | r,w | 0x0031 |
| 12 | Set OVP | unsigned short | 2 | r,w | 0x0020 |
| 13 | Set OCP | unsigned short | 2 | r,w | 0x0021 |
| 14 | Set OPP | unsigned short? | 2 | r,w | 0x0022,0x0023 |
| 15 | Set Comm Address | byte (1-250) | 0 |  r,w | 0x9999 |

**Notes**  
#1 See bit field below from documentation.   
#3 no idea  
#4 when it's reading 0x0233 that equals voltage has 2 decimal places, current 3, power 3  
#7, #14 Two 16 bit registers are used to make one 32 bit value.  
#14 type (range as it's called in docs) says 0-65535 (unsigned short) but I question that since it's a combination of two registers like #7
#15 docs say the range is 1-250, not sure of the best type to use for that, although not using a type in python. 

```
// protection status bit

union _ST
{
  struct
  {
    uint8_t isOVP:1；//Over voltage protection 
    uint8_t isOCP:1；//Over current protection
    uint8_t isOPP:1；//Over power protection
    uint8_t isOTP:1；//Over tempreture protection
    uint8_t isSCP:1；//short-circuit protection
  }OP;
  uint8_t Dat;
｝
```

Some previous work on the topic

http://www.roedan.com/controlling-a-cheap-usb-power-supply/  
https://bitbucket.org/roedan/powersupply/src/master/  
http://nightflyerfireworks.com/home/fun-with-cheap-programable-power-supplies

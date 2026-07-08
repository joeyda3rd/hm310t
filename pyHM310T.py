from pymodbus.client import ModbusSerialClient as ModbusClient
from pymodbus.exceptions import ModbusIOException

class PowerSupplyCommunicationError(Exception):
    pass

class PowerSupply:
    def __init__(self, port, baudrate=9600, slave=1, voltage_limit=30.0, current_limit=10.0):
        self.voltage_limit = voltage_limit  # Voltage limit in volts
        self.current_limit = current_limit  # Current limit in amps
        self.slave = slave
        
        self.client = ModbusClient(method='rtu', port=port, baudrate=baudrate)
        if not self.client.connect():
            raise PowerSupplyCommunicationError("Failed to connect to the power supply")
        # Attempt to read a known register as a connectivity check
        try:
            result = self.client.read_holding_registers(0x0001, count=1, slave=slave)
            if result.isError():
                raise PowerSupplyCommunicationError("Unable to read from power supply")
        except Exception as e:
            raise PowerSupplyCommunicationError("Communication error with power supply: " + str(e)) 


    def read_register(self, address):
        try:
            response = self.client.read_holding_registers(address, count=1, slave=self.slave)
            if response.isError():
                print(f"Error reading register {address}: {response}")
            else:
                return response.registers[0]
        except ModbusIOException as e:
            print(f"Modbus IO Exception reading register {address}: {e}")

    def write_register(self, address, value):
        try:
            response = self.client.write_register(address, value, slave=self.slave)
            if response.isError():
                print(f"Error writing to register {address}: {response}")
        except ModbusIOException as e:
            print(f"Modbus IO Exception writing to register {address}: {e}")

    def close(self):
        self.client.close()

    def enable_output(self, enable=True):
        """Enables or disables the output."""
        self.write_register(0x0001, int(enable))

    def disable_output(self):
        self.enable_output(enable=False)

    def is_output_enabled(self):
        """Returns whether the output is currently enabled."""
        return bool(self.read_register(0x0001))

    def set_voltage(self, voltage):
        """Sets the voltage."""
        if voltage < 0 or voltage > self.voltage_limit:
            print(f"Warning: Voltage must be between 0 and {self.voltage_limit}V. Setting voltage to nearest limit.")
            voltage = max(0, min(voltage, self.voltage_limit))
        self.write_register(0x0030, int(voltage * 100))

    def get_voltage(self):
        """Returns the current voltage setting."""
        return self.read_register(0x0030) / 100.0

    def set_current(self, current):
        """Sets the current."""
        if current < 0 or current > self.current_limit:
            print(f"Warning: Current must be between 0 and {self.current_limit}A. Setting current to nearest limit.")
            current = max(0, min(current, self.current_limit))
        self.write_register(0x0031, int(current * 1000))

    def get_current(self):
        """Returns the current current setting."""
        return self.read_register(0x0031) / 1000.0

    def get_voltage_display(self):
        """Returns the current voltage display value."""
        return self.read_register(0x0010) / 100.0

    def get_current_display(self):
        """Returns the current current display value."""
        return self.read_register(0x0011) / 1000.0

    def get_power_display(self):
        """Returns the current power display value."""
        power_high = self.read_register(0x0012)
        power_low = self.read_register(0x0013)
        return (power_high * 65536 + power_low) / 1000.0  # The register values are combined and divided by 1000 to convert them to a power with 3 decimal places

    def get_comm_address(self):
        """Returns the current communication address."""
        return self.read_register(0x9999)

    def set_comm_address(self, address):
        """Sets the communication address."""
        if address < 1 or address > 250:
            raise ValueError("Address must be between 1 and 250")
        self.write_register(0x9999, address)
        self.slave = address

    def get_protection_status(self):
        status = self.read_register(0x0002)
        return {
            'isOVP': bool(status & 0x01),
            'isOCP': bool(status & 0x02),
            'isOPP': bool(status & 0x04),
            'isOTP': bool(status & 0x08),
            'isSCP': bool(status & 0x10),
        }

    def get_ovp(self):
        return self.read_register(0x0020) / 100.0

    def set_ovp(self, ovp):
        if ovp < 0:
            ovp = 0
        elif ovp > 30:
            ovp = 30
        self.write_register(0x0020, int(ovp * 100))

    def get_ocp(self):
        return self.read_register(0x0021) / 100.0

    def set_ocp(self, ocp):
        if ocp < 0:
            ocp = 0
        elif ocp > 10:
            ocp = 10
        self.write_register(0x0021, int(ocp * 100))

    def get_opp(self):
        high = self.read_register(0x0022)
        low = self.read_register(0x0023)
        return (high << 16 | low) / 100.0

    def set_opp(self, opp):
        if opp < 0:
            opp = 0
        elif opp > 300:
            opp = 300
        value = int(opp * 100)
        high = (value >> 16) & 0xFFFF
        low = value & 0xFFFF
        self.write_register(0x0022, high)
        self.write_register(0x0023, low)

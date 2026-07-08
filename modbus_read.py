import time
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusIOException

def run():
	print("Creating client")
	client = ModbusSerialClient("/dev/ttyUSB0", method='rtu', baudrate=9600, stopbits=1, parity='N', bytesize=8, timeout=1, slave=1)

	print("Connecting to client")
	if not client.connect():
        	print("Failed to connect to client")
        	return

	# List of register addresses to read from
	register_addresses = [0x01, 0x02, 0x03, 0x04, 0x05, 0x10, 0x11, 0x12, 0x13, 0x30, 0x31, 0x20, 0x21, 0x22, 0x23, 0x9999]

	# Read from each register
	for address in register_addresses:
		try:
			response = client.read_holding_registers(address, count=1)
			if response.isError():
				print(f"Error reading register {address}: {response}")
			else:
				print(f"Register {address}: {response.registers}")
			time.sleep(0.035)
		except ModbusIOException as e:
			print(f"Modbus IO Exception reading register {address}: {e}")

	print("Closing client")
	client.close()

run()

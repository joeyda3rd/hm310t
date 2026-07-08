from setuptools import setup

setup(
    name='pyHM310T',
    version='0.1.0',
    description='Python library for controlling the Hanmatek HM310T power supply',
    author='Joey Marino',
    author_email='joey.da3rd@gmail.com',
    url='https://github.com/joeyda3rd/modbus-power-supply',
    py_modules=['pyHM310T'],
    install_requires=[
        'pymodbus',
        'pyserial',
    ],
)

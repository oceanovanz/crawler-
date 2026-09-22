# Oceanova Crawler ESP32 Controller

Low-level hardware controller for the Oceanova underwater crawler/ROV.

The ESP32 handles motor control, IMU acquisition and rotating sonar measurements. It communicates with the Raspberry Pi over USB serial at **115200 baud**.

## Hardware

### Target hardware

* ESP32-WROOM-32 / classic ESP32 DevKit
* 2 × IBT-2 / BTS7960 motor drivers
* 2 × DC motors
* BNO085 IMU
* *Prototype ground mode* 
    * HC-SR04 ultrasonic sensor
    * SG90 servo for rotating the HC-SR04

### Motor drivers

| Function      | ESP32 GPIO |
| ------------- | ---------: |
| Left RPWM     |    GPIO 25 |
| Left LPWM     |    GPIO 26 |
| Right RPWM    |    GPIO 32 |
| Right LPWM    |    GPIO 33 |
| Driver enable |     GPIO 4 |

The motor drivers are controlled using PWM. Motor commands range from `-1000` to `+1000`.

The right motor is currently configured as inverted in software.

### BNO085 IMU

| BNO085  | ESP32   |
| ------- | ------- |
| VCC/VIN | 3.3 V   |
| GND     | GND     |
| SDA     | GPIO 21 |
| SCL     | GPIO 22 |
| RST     | GPIO 27 |

I2C is configured for 100 kHz.

The BNO085 may use I2C address `0x4A` or `0x4B`; the software probes both.

For I2C operation, P0/PS0 and P1/PS1 should not be pulled high.

### Rotating sonar

| Component    | ESP32 GPIO |
| ------------ | ---------: |
| Servo signal |    GPIO 16 |
| HC-SR04 TRIG |     GPIO 5 |
| HC-SR04 ECHO |    GPIO 18 |

The servo and ESP32 must share a common ground. The servo should have an appropriate 5 V supply rather than relying on the ESP32 3.3 V rail.

## Software setup

### Arduino IDE

Install the Arduino IDE and add ESP32 board support through the Arduino Boards Manager.

Select an ESP32-WROOM-32 / ESP32 Dev Module board matching the hardware.

Connect the ESP32 over USB and select the appropriate serial port.

### Required libraries

Install the following libraries through the Arduino Library Manager:

* **ESP32Servo** — servo control
* **Adafruit BNO08x** — BNO085/BNO08x IMU
* **Adafruit BusIO** — dependency used by Adafruit libraries

The project also uses standard ESP32/Arduino functionality such as:

* `Arduino.h`
* `Wire.h`
* ESP32 LEDC PWM

Compile and upload the main `.ino` file from Arduino IDE.

## Serial protocol

Commands from the Raspberry Pi:

```text
ARM
M <left> <right>
STOP
DISARM
STATUS
PING
```

Motor commands use values from `-1000` to `+1000`.

While armed, a valid motor command must be received at least every 500 ms. If commands stop arriving, the ESP32 stops and disarms the motors.

### Outgoing messages

Motor/state telemetry:

```text
T,<timestamp>,<left_motor>,<right_motor>,<armed>
```

IMU orientation:

```text
I,<timestamp>,<imu_online>,<orientation_valid>,<yaw>,<pitch>,<roll>
```

Sonar:

```text
S,<timestamp>,<sonar_online>,<angle>,<distance>
```

All timestamps are ESP32 `millis()` timestamps.

## Code structure

The code is split into small hardware/protocol modules:

```text
crawler_esp32/
├── crawler_esp32.ino
├── motors.h
├── motors.cpp
├── imu.h
├── imu.cpp
├── sonar.h
├── sonar.cpp
├── serial_protocol.h
└── serial_protocol.cpp
```

### `crawler_esp32.ino`

Main application entry point.

Initialises the hardware and repeatedly services each subsystem:

```cpp
void loop()
{
    serviceSerialProtocol();
    serviceImu();
    serviceMotors();
    serviceSonar();
    serviceTelemetry();
}
```

### `motors.cpp`

Owns:

* Motor PWM outputs
* Target/current motor commands
* Motor ramping
* Armed state
* Motor command watchdog
* Emergency stop/disarm

### `imu.cpp`

Owns:

* BNO085 initialisation
* I2C address detection
* IMU recovery
* Orientation updates
* Yaw/pitch/roll state

### `sonar.cpp`

Owns:

* HC-SR04 measurement
* Servo positioning/sweep
* Sonar timing
* Sonar online state
* Current sonar angle and distance

The serial layer accesses these through functions such as:

```cpp
getSonarDistance()
getSonarAngle()
isSonarOnline()
```

### `serial_protocol.cpp`

Owns:

* Incoming command parsing
* Serial command responses
* Formatting outgoing telemetry
* Communication between the Pi and the hardware modules

The hardware modules do not need to know how their data is transmitted to the Pi.

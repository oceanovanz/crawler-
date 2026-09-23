# Oceanova Crawler

Rapid-prototype tethered freshwater crawler control stack for the Oceanova inspection crawler.

## Current working architecture

```text
WINDOWS TOPSIDE PC
  Sony DualSense
  Pygame operator UI
        |
        | control + telemetry WebSocket :8765
        | JPEG video WebSocket          :8766
        v
RASPBERRY PI
  USB camera + USB serial
        |
        v
ESP32
  BNO085 IMU
  2 x IBT-2 / BTS7960 motor drivers
        |
        v
2 x 24 V geared motors
```

Video and control use separate WebSocket connections so a large JPEG frame cannot delay STOP or steering commands.

## Repository layout

```text
esp32/
  oceanova_crawler_esp32_i2c.ino       Current BNO085 I2C firmware
  oceanova_crawler_esp32_spi.ino       Earlier SPI version

pi/
  oceanova_pi_ws_bridge_system.py      Current Raspberry Pi crawler bridge
  oceanova_thonny_camera_esp32.py      Camera + ESP32 bench test
  crawler_stream.py                    Browser MJPEG prototype
  oceanova_crawler_v1.py               Earlier local Pi controller
  systemd/
    oceanova-crawler.service           Raspberry Pi boot service

windows/
  src/main.py                          DualSense topside controller

prototypes/
  earlier WebSocket revisions
```

## Software Versions

There are currently two active software versions for the crawler:
- `v1`: manual only version 
  - Supports direct control of the crawler using joystick commands
- `v2`: first semi-autonomous version
  - Supports direct control of the crawler using joystick commands
  - Has route planning options in the topside application
  - ROS2 navigation and localisation integration in `crawler_pi`
  - Supports AUTO mode where the crawler follows the planned route autonomously
  - Note: doesn't yet support SLAM / automatic map making

### Switching between versions

To use v1:
```bash
git checkout --recurse-submodules v1
```

To use v2:
```bash
git checkout --recurse-submodules main
```

Note: make sure the raspberry pi is on the same branch as the topside.

## Current DualSense controls

The current topside controller intentionally has **no hold-to-run deadman**.

```text
OPTIONS / START   ARM
CIRCLE            immediate STOP + DISARM
Left stick Y      forward / reverse
Right stick X     skid steering
S                 STOP + DISARM
P                 ping Raspberry Pi
Q / ESC           STOP + quit
```

Once armed, valid stick input can command the crawler directly.

Safety behaviour retained in the topside controller:

- starts disarmed
- controller disconnect sends STOP
- window focus loss sends STOP
- stale telemetry sends STOP
- control-link loss clears local drive commands
- reconnect never automatically re-arms
- Pi command watchdog remains active
- ESP32 command watchdog remains active

## ESP32

`crawler_esp32` contains the firmware for the esp32. This controls the IMU, motors, and ultrasonic sensor.

See the [esp32 README](crawler_esp32/README.md) for details on the target hardware, wiring setup, and the serial protocol.

## Raspberry Pi

`crawler_pi` contains the codebase for the raspberry pi. This acts as the bridge between the topside user interface, robot hardware, and serial communication to the esp32.

The websocket server communicates to the topside client:

```text
TCP 8765   control + telemetry
TCP 8766   JPEG video
```

The serial bridge automatically searches for the ESP32 under:

```text
/dev/serial/by-id/*
/dev/ttyACM*
/dev/ttyUSB*
```

See the [pi README](crawler_pi/README.md) for details on the raspberry pi setup and codebase.

## Windows Topside

`windows` contains the code base for the topside user application and websocket client to commuicate to the raspberry pi.

The application can either be run from the terminal (developer mode):
```bash
python3 windows/src/main.py
```

or by directly running the executable.

See the [windows README](windows/README.md) for details on the application code base and instructions on how to create a new windows executable.


## Dedicated Ethernet addressing

For the dedicated tether configuration:

```text
Windows Ethernet: 192.168.10.1/24
Crawler Pi eth0:  192.168.10.2/24
```

Temporary Pi setup:

```bash
sudo ip addr add 192.168.10.2/24 dev eth0
sudo ip link set eth0 up
```

Then from Windows:

```powershell
ping 192.168.10.2
Test-NetConnection 192.168.10.2 -Port 8765
Test-NetConnection 192.168.10.2 -Port 8766
```

## WebSocket protocol

Control + telemetry endpoint:

```text
ws://<PI_IP>:8765
```

Video endpoint:

```text
ws://<PI_IP>:8766
```

Topside messages include:

```json
{"type":"ping","client_time":1234567890.0}
{"type":"arm"}
{"type":"stop"}
{"type":"motor","left":1000,"right":1000}
```

The Pi sends telemetry JSON derived from the ESP32 serial telemetry and binary JPEG frames on the video socket.

## Failsafe chain

```text
Topside command stream stops
        |
        v
Pi command watchdog (~350 ms)
        |
        v
STOP to ESP32

Pi / USB / software fails
        |
        v
ESP32 command watchdog (~500 ms)
        |
        v
motor outputs disabled
```

The Pi also sends STOP when a control client connects or disconnects.

## PoE topology

Current topside switch: Grandstream GWN7700P PoE+.

```text
Windows PC
   |
GWN7700P
   |
   | 100 m Ethernet data + PoE
   v
active IEEE 802.3af/at splitter
   |-- Ethernet -> Raspberry Pi
   `-- regulated 5 V -> Raspberry Pi power
```

The 24 V propulsion motors remain powered from the onboard battery, not PoE.

## Development status

The following have now been proven in the prototype stack:

- USB crawler camera
- Raspberry Pi JPEG video streaming
- ESP32 serial telemetry
- BNO085 orientation telemetry
- Windows/Pi WebSocket communication
- Sony DualSense topside control
- skid-steer motor control
- full `-1000..+1000` command range
- layered Pi + ESP32 watchdogs

Next likely work includes operator UI polish, cruise/long-run behaviour if useful, depth/leak/battery sensing, and further underwater trials.

## Safety

This repository controls powered machinery. Keep an immediate STOP available, use suitable battery protection and isolation, waterproof all submerged penetrations and electronics, retain a separate mechanical recovery line, and use staged bench/shallow-water testing before deeper operation.

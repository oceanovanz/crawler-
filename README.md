# Oceanova Crawler

Rapid-prototype tethered freshwater crawler control stack for the Oceanova 7 m inspection crawler.

## Current architecture

```text
TOPSIDE WINDOWS PC
        |
        | 100 m Ethernet
        | control/telemetry WebSocket :8765
        | video WebSocket             :8766
        v
RASPBERRY PI
   |-- USB camera (/dev/video0)
   |-- USB serial (115200)
   v
ESP32
   |-- BNO085 IMU over I2C
   |-- 2 x IBT-2 / BTS7960 motor drivers
   v
2 x 24 V geared motors
```

The current prototype deliberately keeps video and control on separate WebSockets so a large JPEG video frame cannot delay a STOP or steering command.

## Repository layout

```text
esp32/
  oceanova_crawler_esp32_spi.ino      Earlier BNO085 SPI version
  oceanova_crawler_esp32_i2c.ino      Current BNO085 I2C crawler firmware

pi/
  oceanova_pi_ws_bridge_system.py     Current Raspberry Pi Ethernet bridge
  oceanova_thonny_camera_esp32.py     Local camera + ESP32 telemetry bench test
  crawler_stream.py                   Browser MJPEG/telemetry prototype
  oceanova_crawler_v1.py              Local DualSense/camera/ESP32 skid-steer prototype

windows/
  oceanova_windows_ws_viewer_system.py  Current Windows Ethernet viewer

prototypes/
  oceanova_pi_ws_bridge.py             Earlier WebSocket bridge revision
  oceanova_windows_ws_viewer.py        Earlier Windows viewer revision
```

## Hardware

Current prototype hardware includes:

- Raspberry Pi
- ESP32 DevKit / ESP32-WROOM-32
- BNO085 IMU
- 2 x IBT-2 / BTS7960 H-bridge motor drivers
- 2 x 24 V geared motors
- USB camera
- Sony DualSense controller
- 100 m Ethernet tether
- 24 V onboard motor battery
- Topside Grandstream GWN7700P PoE+ switch
- Suitable active IEEE 802.3af/at PoE splitter at the Raspberry Pi end when powering the Pi from topside

The motors remain powered from the onboard 24 V battery. PoE is intended for the Raspberry Pi, camera and ESP32 electronics, not the motor load.

## ESP32 pin map

### Motor drivers

| Function | ESP32 |
|---|---:|
| Left IBT-2 RPWM | GPIO 25 |
| Left IBT-2 LPWM | GPIO 26 |
| Right IBT-2 RPWM | GPIO 32 |
| Right IBT-2 LPWM | GPIO 33 |
| Both IBT-2 R_EN + L_EN | GPIO 4 |

Use a 10 kOhm pulldown from GPIO 4 to GND so the drivers remain disabled during boot.

Each motor connects to the M+ / M- outputs of its IBT-2. Motors do **not** connect directly to ESP32 GPIO.

### BNO085 — current I2C configuration

| BNO085 | ESP32 |
|---|---:|
| VIN / VCC | 3.3 V |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |

The current firmware probes both `0x4A` and `0x4B` at startup.

## ESP32 serial protocol

Baud rate: `115200`

Commands from Raspberry Pi to ESP32:

```text
ARM
STOP
DISARM
PING
STATUS
M <left> <right>
```

Motor values are signed integers from `-1000` to `+1000`.

Example:

```text
M 250 220
```

The ESP32 requires valid motor commands while armed. Its watchdog stops/disarms if commands stop arriving for approximately 500 ms.

### Telemetry

ESP32 telemetry is emitted approximately every 100 ms:

```text
T,time_ms,yaw,pitch,roll,left_motor,right_motor,armed,imu_online,orientation_valid
```

Example:

```text
T,55476,121.89,70.88,171.65,0,0,0,1,1
```

Fields:

- `time_ms` — ESP32 uptime
- `yaw` — relative yaw in degrees
- `pitch` — pitch in degrees
- `roll` — roll in degrees
- `left_motor` — current left motor command
- `right_motor` — current right motor command
- `armed` — 0/1
- `imu_online` — 0/1
- `orientation_valid` — 0/1

The BNO085 currently uses Game Rotation Vector, so yaw is relative and may drift. There is currently no underwater position estimate.

## Raspberry Pi setup

The current Pi bridge is designed to use normal Raspberry Pi OS system Python; no virtual environment is required.

Install dependencies:

```bash
sudo apt update
sudo apt install -y \
  python3-opencv \
  python3-serial \
  python3-websockets
```

Confirm the modern websockets API is available:

```bash
python3 -c "import websockets; print(websockets.__version__); from websockets.asyncio.server import serve; print('ASYNCIO API OK')"
```

Run the current bridge:

```bash
python3 pi/oceanova_pi_ws_bridge_system.py
```

It opens:

- `/dev/video0` for the USB camera
- an ESP32 serial device found under `/dev/serial/by-id/*`, `/dev/ttyACM*` or `/dev/ttyUSB*`
- WebSocket control/telemetry on TCP `8765`
- WebSocket JPEG video on TCP `8766`

## Direct Ethernet test addressing

A simple prototype network is:

```text
Windows topside: 192.168.10.1/24
Crawler Pi:      192.168.10.2/24
```

Temporary Pi configuration:

```bash
sudo ip addr flush dev eth0
sudo ip addr add 192.168.10.2/24 dev eth0
sudo ip link set eth0 up
```

Then verify from Windows:

```powershell
ping 192.168.10.2
```

## WebSocket protocol

### Control + telemetry

Endpoint:

```text
ws://192.168.10.2:8765
```

Topside to Pi:

```json
{"type":"ping","client_time":1234567890.0}
{"type":"arm"}
{"type":"stop"}
{"type":"motor","left":250,"right":220}
```

Pi telemetry to topside:

```json
{
  "type": "telemetry",
  "esp32_time_ms": 55476,
  "yaw": 121.89,
  "pitch": 70.88,
  "roll": 171.65,
  "left_motor": 0,
  "right_motor": 0,
  "armed": false,
  "imu_online": true,
  "orientation_valid": true
}
```

### Video

Endpoint:

```text
ws://192.168.10.2:8766
```

Each binary WebSocket message contains one complete JPEG frame.

The current prototype uses 640 x 480 at around 20 fps and JPEG quality 70. This is intentionally simple for initial link testing. A later version may move video to H.264/GStreamer or WebRTC while retaining WebSockets for low-latency control.

## Failsafes

The control chain is intentionally layered:

```text
Topside stops sending commands
        |
        v
Pi command watchdog (~350 ms)
        |
        v
STOP sent to ESP32

Pi / USB / software fails
        |
        v
ESP32 command watchdog (~500 ms)
        |
        v
motor drivers disabled
```

The Pi bridge also sends STOP when a control client connects or disconnects.

For initial testing, keep the crawler wheels off the ground and use low motor command limits.

## PoE topology

The Grandstream GWN7700P can act as the topside IEEE 802.3af/at PoE source.

```text
Windows PC
   |
   v
GWN7700P PoE+ switch
   |
   | 100 m Ethernet: data + PoE
   v
active PoE splitter
   |-- Ethernet -> Raspberry Pi Ethernet
   `-- regulated 5 V -> Raspberry Pi power input
```

Use an active standards-compliant splitter with adequate 5 V current for the specific Raspberry Pi model. Do not use the PoE link to power the two 24 V propulsion motors.

## Development status

Current focus:

1. Prove USB camera video over the 100 m Ethernet tether.
2. Prove ESP32/BNO085 telemetry reaches the Windows topside computer.
3. Add DualSense skid-steer commands to the topside client at approximately 20 Hz.
4. Build the full topside operator control page.
5. Add additional sensors such as depth, leak detection, motor current and battery voltage.

## Safety

This repository contains rapid-prototype control software for powered machinery. Bench-test with wheels raised before wet testing. Use an accessible battery fuse/isolation method, common logic grounds, proper waterproof penetrations, a separate mechanical recovery line, and conservative staged depth testing.

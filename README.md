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
  /home/oceanovatest/Desktop/crawler.py
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

windows/
  crawler_topside.py                    Current DualSense topside controller
  oceanova_windows_ws_viewer_system.py Earlier non-driving viewer

systemd/
  oceanova-crawler.service             Raspberry Pi boot service

prototypes/
  earlier WebSocket revisions
```

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

## Motor command range

The ESP32 command protocol uses signed values from `-1000` to `+1000`.

```text
-1000  full requested reverse PWM
0      stop
+1000  full requested forward PWM
```

The current topside controller uses the full `1000 / 1000` range.

The ESP32 firmware uses 10-bit PWM (`0..1023`) and maps command magnitude `1000` to full PWM duty. A ramp remains in the ESP32 firmware to avoid instantaneous command steps.

## ESP32 motor pin map

| Function | ESP32 |
|---|---:|
| Left IBT-2 RPWM | GPIO 25 |
| Left IBT-2 LPWM | GPIO 26 |
| Right IBT-2 RPWM | GPIO 32 |
| Right IBT-2 LPWM | GPIO 33 |
| Both IBT-2 R_EN + L_EN | GPIO 4 |

Use a 10 kOhm pulldown from GPIO 4 to GND so the drivers remain disabled during boot.

## BNO085 I2C wiring

| BNO085 | ESP32 |
|---|---:|
| VIN / VCC | 3.3 V |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |

The firmware probes `0x4A` then `0x4B` at startup and currently uses Game Rotation Vector for relative yaw, pitch and roll.

## ESP32 serial protocol

Baud rate: `115200`

Commands:

```text
ARM
STOP
DISARM
PING
STATUS
M <left> <right>
```

Example:

```text
M 1000 1000
```

Telemetry is emitted approximately every 100 ms:

```text
T,time_ms,yaw,pitch,roll,left_motor,right_motor,armed,imu_online,orientation_valid
```

Example:

```text
T,55476,121.89,70.88,171.65,0,0,0,1,1
```

## Raspberry Pi setup

The crawler bridge uses normal Raspberry Pi OS system Python.

Install dependencies:

```bash
sudo apt update
sudo apt install -y python3-opencv python3-serial python3-websockets
```

The current deployed Pi script is:

```text
/home/oceanovatest/Desktop/crawler.py
```

The repository equivalent is:

```text
pi/oceanova_pi_ws_bridge_system.py
```

Run manually:

```bash
python3 /home/oceanovatest/Desktop/crawler.py
```

The bridge listens on all interfaces:

```text
TCP 8765   control + telemetry
TCP 8766   JPEG video
```

It automatically searches for the ESP32 under:

```text
/dev/serial/by-id/*
/dev/ttyACM*
/dev/ttyUSB*
```

## Raspberry Pi autostart

The repo contains:

```text
systemd/oceanova-crawler.service
```

Install it on the Pi with:

```bash
sudo cp systemd/oceanova-crawler.service /etc/systemd/system/
sudo usermod -aG video,dialout oceanovatest
sudo systemctl daemon-reload
sudo systemctl enable oceanova-crawler.service
sudo systemctl start oceanova-crawler.service
```

Check status:

```bash
systemctl status oceanova-crawler
```

Watch logs:

```bash
journalctl -u oceanova-crawler.service -f
```

The service runs:

```text
/usr/bin/python3 /home/oceanovatest/Desktop/crawler.py
```

and automatically restarts the bridge after a process failure.

## Windows topside setup

Install Python dependencies into the Python installation used to run the controller:

```powershell
python -m pip install pygame numpy websockets opencv-python
```

Run the current controller:

```powershell
python windows\crawler_topside.py
```

The current default Pi address is `192.168.88.5`. Override it without editing the file:

```powershell
python windows\crawler_topside.py --pi 192.168.10.2
```

This makes it easy to use either the current `192.168.88.x` test network or the dedicated tether subnet later.

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

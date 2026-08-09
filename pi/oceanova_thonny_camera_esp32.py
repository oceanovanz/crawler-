#!/usr/bin/env python3
"""
Oceanova crawler - camera + ESP32 telemetry bench test

Designed to run directly from Thonny on a Raspberry Pi.

What it does:
  - Opens USB camera /dev/video0
  - Automatically finds the ESP32 USB serial port
  - Reads BNO085 and motor telemetry from the ESP32
  - Displays telemetry over the live camera image
  - Sends STOP at startup and shutdown
  - Does NOT arm or drive the motors

Keyboard:
  Q or Esc  Quit safely
  S         Request one STATUS message
  P         Send PING
"""

from __future__ import annotations

import glob
import time

import cv2
import serial

CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 20
SERIAL_PORT = "auto"
SERIAL_BAUD = 115200
WINDOW_NAME = "Oceanova Crawler - Camera and ESP32"


def find_esp32_port() -> str:
    if SERIAL_PORT != "auto":
        return SERIAL_PORT
    candidates: list[str] = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        candidates.extend(sorted(glob.glob(pattern)))
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        raise RuntimeError(
            "No ESP32 serial port found.\n"
            "Check the USB cable, then run:\n"
            "  python3 -m serial.tools.list_ports"
        )
    print("Serial devices found:")
    for candidate in candidates:
        print(f"  {candidate}")
    return candidates[0]


def send_command(port: serial.Serial, command: str) -> None:
    port.write((command + "\n").encode("ascii"))
    port.flush()
    print(f"Sent: {command}")


def parse_telemetry(line: str) -> dict:
    fields = [field.strip() for field in line.split(",")]
    if len(fields) != 10 or fields[0] != "T":
        return {}
    try:
        return {
            "time_ms": int(fields[1]),
            "yaw": float(fields[2]),
            "pitch": float(fields[3]),
            "roll": float(fields[4]),
            "left": int(fields[5]),
            "right": int(fields[6]),
            "armed": bool(int(fields[7])),
            "imu_online": bool(int(fields[8])),
            "orientation_valid": bool(int(fields[9])),
        }
    except ValueError:
        return {}


def read_serial_lines(port: serial.Serial, telemetry: dict, latest_line: str) -> tuple[dict, str]:
    while port.in_waiting > 0:
        raw = port.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        latest_line = line
        print(f"ESP32: {line}")
        parsed = parse_telemetry(line)
        if parsed:
            telemetry = parsed
    return telemetry, latest_line


def draw_text(frame, text: str, line_number: int, colour: tuple[int, int, int] = (255, 255, 255)) -> None:
    x = 12
    y = 28 + line_number * 28
    cv2.putText(frame, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, colour, 1, cv2.LINE_AA)


def draw_status(frame, telemetry: dict, latest_line: str, serial_device: str) -> None:
    draw_text(frame, f"ESP32: {serial_device}", 0)
    if telemetry:
        imu_ok = telemetry["imu_online"] and telemetry["orientation_valid"]
        imu_colour = (0, 255, 0) if imu_ok else (0, 165, 255)
        armed_colour = (0, 0, 255) if telemetry["armed"] else (0, 255, 0)
        draw_text(frame, f"Yaw {telemetry['yaw']:.1f}  Pitch {telemetry['pitch']:.1f}  Roll {telemetry['roll']:.1f}", 1)
        draw_text(frame, f"IMU {'ONLINE' if imu_ok else 'NOT READY'}", 2, imu_colour)
        draw_text(frame, f"Motors L {telemetry['left']:+d}  R {telemetry['right']:+d}", 3)
        draw_text(frame, "ARMED" if telemetry["armed"] else "DISARMED", 4, armed_colour)
    else:
        draw_text(frame, "Waiting for telemetry...", 1, (0, 165, 255))
    draw_text(frame, f"Latest: {latest_line[:65]}", 5)
    draw_text(frame, "Q quit | S status | P ping", 6)


def main() -> None:
    camera = None
    esp32 = None
    try:
        camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
        if not camera.isOpened():
            camera.release()
            camera = cv2.VideoCapture(CAMERA_INDEX)
        if not camera.isOpened():
            raise RuntimeError(f"Could not open camera index {CAMERA_INDEX}")

        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        camera.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = camera.get(cv2.CAP_PROP_FPS)
        print(f"Camera open: /dev/video{CAMERA_INDEX}, {actual_width}x{actual_height} at {actual_fps:.1f} fps")

        serial_device = find_esp32_port()
        print(f"Opening ESP32 on {serial_device}")
        esp32 = serial.Serial(
            port=serial_device,
            baudrate=SERIAL_BAUD,
            timeout=0,
            write_timeout=0.5,
            rtscts=False,
            dsrdtr=False,
        )
        time.sleep(2.0)
        try:
            esp32.dtr = False
            esp32.rts = False
        except OSError:
            pass
        esp32.reset_input_buffer()
        send_command(esp32, "STOP")
        time.sleep(0.1)
        send_command(esp32, "PING")
        send_command(esp32, "STATUS")

        telemetry: dict = {}
        latest_line = "No serial data yet"
        print("\nCamera and ESP32 are open.")
        print("Press Q or Esc in the camera window to stop.\n")

        while True:
            telemetry, latest_line = read_serial_lines(esp32, telemetry, latest_line)
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("Camera frame read failed")
            draw_status(frame, telemetry, latest_line, serial_device)
            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                print("Quit requested")
                break
            if key == ord("s"):
                send_command(esp32, "STATUS")
            if key == ord("p"):
                send_command(esp32, "PING")

    except KeyboardInterrupt:
        print("\nKeyboard interrupt")
    except (RuntimeError, serial.SerialException, OSError) as error:
        print(f"\nERROR: {error}")
    finally:
        if esp32 is not None and esp32.is_open:
            try:
                for _ in range(3):
                    send_command(esp32, "STOP")
                    time.sleep(0.03)
            except (serial.SerialException, OSError):
                pass
            esp32.close()
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        print("Camera and ESP32 closed safely")


if __name__ == "__main__":
    main()

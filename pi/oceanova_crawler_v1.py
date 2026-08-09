#!/usr/bin/env python3
"""
Oceanova crawler - first Raspberry Pi control test

Hardware:
  - USB camera at /dev/video0
  - Sony DualSense controller connected to the Raspberry Pi
  - ESP32 connected to the Raspberry Pi by USB serial

Controls:
  OPTIONS     Arm the ESP32
  CIRCLE      Stop and disarm immediately
  Hold L1     Deadman enable: motors may move only while held
  Left stick  Forward/reverse
  Right stick Left/right steering
  Q or ESC    Stop, disarm, and quit

ESP32 protocol:
  ARM
  M <left> <right>       values -1000 to +1000
  STOP
"""

from __future__ import annotations

import glob
import os
import sys
import time
from typing import Optional

os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import cv2
except ImportError:
    raise SystemExit("OpenCV is missing.\nInstall it with:\n  sudo apt install -y python3-opencv")

try:
    import pygame
    from pygame._sdl2 import controller as sdl2_controller
except ImportError:
    raise SystemExit("Pygame is missing.\nInstall it with:\n  sudo apt install -y python3-pygame")

try:
    import serial
except ImportError:
    raise SystemExit("pySerial is missing.\nInstall it with:\n  sudo apt install -y python3-serial")

CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
SERIAL_PORT = "auto"
SERIAL_BAUD = 115200
MAX_COMMAND = 300
DEADZONE = 0.12
COMMAND_RATE_HZ = 20.0
THROTTLE_SIGN = 1.0
STEERING_SIGN = 1.0
WINDOW_NAME = "Oceanova Crawler - Bench Test"


def find_serial_port(requested: str) -> str:
    if requested != "auto":
        return requested
    candidates: list[str] = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        candidates.extend(sorted(glob.glob(pattern)))
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        raise RuntimeError("No ESP32 serial port found. Check the USB cable and run:\n  python3 -m serial.tools.list_ports")
    return candidates[0]


def send_line(port: serial.Serial, text: str) -> None:
    port.write((text + "\n").encode("ascii"))


def apply_deadzone(value: float, deadzone: float) -> float:
    if abs(value) <= deadzone:
        return 0.0
    magnitude = (abs(value) - deadzone) / (1.0 - deadzone)
    return magnitude if value > 0.0 else -magnitude


def controller_axis(controller: sdl2_controller.Controller, axis: int) -> float:
    raw = controller.get_axis(axis)
    return max(-1.0, min(1.0, raw / 32767.0))


def skid_steer_mix(throttle: float, steering: float) -> tuple[int, int]:
    left = throttle + steering
    right = throttle - steering
    peak = max(1.0, abs(left), abs(right))
    left /= peak
    right /= peak
    return (int(round(left * MAX_COMMAND)), int(round(right * MAX_COMMAND)))


def open_controller() -> sdl2_controller.Controller:
    pygame.init()
    pygame.display.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN)
    sdl2_controller.init()
    count = sdl2_controller.get_count()
    if count == 0:
        raise RuntimeError("No game controller found. Connect the DualSense by USB and press PS.")
    for index in range(count):
        name = sdl2_controller.name_forindex(index)
        print(f"Controller device {index}: {name}")
        if sdl2_controller.is_controller(index):
            gamepad = sdl2_controller.Controller(index)
            print(f"Using controller: {name}")
            return gamepad
    raise RuntimeError("A joystick was detected, but SDL did not recognise it as a game controller.")


def open_camera() -> cv2.VideoCapture:
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
    width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = camera.get(cv2.CAP_PROP_FPS)
    print(f"Camera opened: /dev/video{CAMERA_INDEX}, {width}x{height} at {fps:.1f} fps")
    return camera


def open_esp32() -> tuple[serial.Serial, str]:
    device = find_serial_port(SERIAL_PORT)
    print(f"Opening ESP32 serial port: {device}")
    port = serial.Serial(port=device, baudrate=SERIAL_BAUD, timeout=0, write_timeout=0.2, rtscts=False, dsrdtr=False)
    try:
        port.dtr = False
        port.rts = False
    except OSError:
        pass
    time.sleep(2.0)
    port.reset_input_buffer()
    send_line(port, "STOP")
    time.sleep(0.05)
    return port, device


def read_latest_serial_line(port: serial.Serial, previous: str) -> str:
    latest = previous
    while port.in_waiting:
        raw = port.readline()
        if not raw:
            break
        text = raw.decode("utf-8", errors="replace").strip()
        if text:
            latest = text
            print(f"ESP32: {text}")
    return latest


def draw_text(frame, text: str, line: int, colour: tuple[int, int, int] = (255, 255, 255)) -> None:
    x = 12
    y = 28 + line * 28
    cv2.putText(frame, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, colour, 1, cv2.LINE_AA)


def main() -> int:
    camera: Optional[cv2.VideoCapture] = None
    esp32: Optional[serial.Serial] = None
    gamepad: Optional[sdl2_controller.Controller] = None
    armed = False
    previous_options = False
    previous_circle = False
    latest_serial = "No telemetry yet"
    left_command = 0
    right_command = 0
    throttle = 0.0
    steering = 0.0
    next_command_time = time.monotonic()
    command_period = 1.0 / COMMAND_RATE_HZ

    try:
        gamepad = open_controller()
        camera = open_camera()
        esp32, serial_device = open_esp32()
        print("\nControls:")
        print("  OPTIONS     arm")
        print("  CIRCLE      stop and disarm")
        print("  Hold L1     deadman enable")
        print("  Left stick  forward/reverse")
        print("  Right stick steering")
        print("  Q or ESC    quit\n")
        print("Keep the wheels off the ground for this first test.")

        while True:
            pygame.event.pump()
            if not gamepad.attached():
                print("Controller disconnected - stopping.")
                send_line(esp32, "STOP")
                armed = False
                break

            options = bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_START))
            circle = bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_B))
            deadman = bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_LEFTSHOULDER))

            if options and not previous_options:
                send_line(esp32, "ARM")
                armed = True
                print("ARM requested")

            if circle and not previous_circle:
                send_line(esp32, "STOP")
                armed = False
                left_command = 0
                right_command = 0
                print("STOP requested")

            previous_options = options
            previous_circle = circle

            left_y = controller_axis(gamepad, pygame.CONTROLLER_AXIS_LEFTY)
            right_x = controller_axis(gamepad, pygame.CONTROLLER_AXIS_RIGHTX)
            throttle = apply_deadzone(-left_y, DEADZONE) * THROTTLE_SIGN
            steering = apply_deadzone(right_x, DEADZONE) * STEERING_SIGN

            if armed and deadman:
                left_command, right_command = skid_steer_mix(throttle, steering)
            else:
                left_command = 0
                right_command = 0

            now = time.monotonic()
            if now >= next_command_time:
                if armed:
                    send_line(esp32, f"M {left_command} {right_command}")
                next_command_time = now + command_period

            latest_serial = read_latest_serial_line(esp32, latest_serial)
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("Camera frame read failed")

            state_text = "ARMED" if armed else "DISARMED"
            state_colour = (0, 220, 255) if armed else (0, 0, 255)
            deadman_text = "L1 HELD" if deadman else "L1 RELEASED"
            draw_text(frame, f"{state_text}  |  {deadman_text}", 0, state_colour)
            draw_text(frame, f"Throttle {throttle:+.2f}  Steering {steering:+.2f}", 1)
            draw_text(frame, f"Motor command  L {left_command:+4d}  R {right_command:+4d}", 2)
            draw_text(frame, f"Limit {MAX_COMMAND}/1000  Serial {serial_device}", 3)
            draw_text(frame, f"ESP32: {latest_serial[:70]}", 4)
            draw_text(frame, "OPTIONS arm | hold L1 drive | CIRCLE stop | Q quit", 5)

            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                print("Operator quit - stopping.")
                break

    except (RuntimeError, serial.SerialException, OSError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return_code = 1
    except KeyboardInterrupt:
        print("\nKeyboard interrupt - stopping.")
        return_code = 0
    else:
        return_code = 0
    finally:
        if esp32 is not None and esp32.is_open:
            for _ in range(3):
                try:
                    send_line(esp32, "STOP")
                    time.sleep(0.03)
                except (serial.SerialException, OSError):
                    break
            try:
                esp32.close()
            except (serial.SerialException, OSError):
                pass
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        if gamepad is not None:
            try:
                gamepad.quit()
            except pygame.error:
                pass
        pygame.quit()

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

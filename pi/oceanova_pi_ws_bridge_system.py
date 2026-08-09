#!/usr/bin/env python3
"""
Oceanova crawler Raspberry Pi WebSocket bridge
SYSTEM PYTHON / THONNY FRIENDLY

Install once on Raspberry Pi OS:
    sudo apt update
    sudo apt install -y python3-opencv python3-serial python3-websockets

Run from Thonny using the normal Local Python 3 interpreter,
or from a terminal with:
    python3 crawler.py

No virtual environment is required.

WebSocket ports:
    8765  Control + telemetry
    8766  Video
"""

from __future__ import annotations

import asyncio
import glob
import json
import signal
import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import serial
from websockets.asyncio.server import serve

HOST = "0.0.0.0"
CONTROL_PORT = 8765
VIDEO_PORT = 8766

CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 20
JPEG_QUALITY = 70

SERIAL_PORT = "auto"
SERIAL_BAUD = 115200
TOPSIDE_WATCHDOG_SECONDS = 0.35
SYSTEM_STATUS_PERIOD_SECONDS = 1.0


def get_primary_ipv4() -> str:
    """Return the Pi's preferred IPv4 address without hard-coding it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packets need to be sent; connect() just lets the OS choose
        # the preferred outbound interface/address.
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


class CameraWorker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="camera", daemon=True)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.latest_jpeg: Optional[bytes] = None
        self.sequence = 0
        self.last_frame_monotonic = 0.0
        self.online = False
        self.error = "Camera not started"
        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0.0

    def snapshot(self):
        with self.lock:
            return (
                self.sequence,
                self.latest_jpeg,
                self.online,
                self.error,
                self.last_frame_monotonic,
                self.actual_width,
                self.actual_height,
                self.actual_fps,
            )

    def _set_error(self, message: str) -> None:
        with self.lock:
            self.online = False
            self.error = message

    def _open_camera(self):
        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(CAMERA_INDEX)
        if not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or float(CAMERA_FPS)

        with self.lock:
            self.online = True
            self.error = ""
            self.actual_width = width
            self.actual_height = height
            self.actual_fps = fps

        print(f"Camera open: /dev/video{CAMERA_INDEX} {width}x{height} @ {fps:.1f} fps")
        return cap

    def run(self) -> None:
        cap = None
        failures = 0
        while not self.stop_event.is_set():
            if cap is None:
                cap = self._open_camera()
                if cap is None:
                    self._set_error(f"Cannot open /dev/video{CAMERA_INDEX}")
                    time.sleep(1.0)
                    continue

            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                self._set_error(f"Camera read failure {failures}")
                if failures >= 10:
                    cap.release()
                    cap = None
                    failures = 0
                time.sleep(0.02)
                continue

            failures = 0
            ok, encoded = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            )
            if not ok:
                self._set_error("JPEG encode failed")
                continue

            with self.lock:
                self.latest_jpeg = encoded.tobytes()
                self.sequence += 1
                self.last_frame_monotonic = time.monotonic()
                self.online = True
                self.error = ""

        if cap is not None:
            cap.release()

    def stop(self) -> None:
        self.stop_event.set()


def serial_candidates() -> list[str]:
    if SERIAL_PORT != "auto":
        return [SERIAL_PORT]
    devices: list[str] = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        devices.extend(sorted(glob.glob(pattern)))
    return list(dict.fromkeys(devices))


def parse_telemetry(line: str) -> Optional[dict]:
    fields = [field.strip() for field in line.split(",")]
    if len(fields) != 10 or fields[0] != "T":
        return None
    try:
        return {
            "type": "telemetry",
            "esp32_time_ms": int(fields[1]),
            "yaw": float(fields[2]),
            "pitch": float(fields[3]),
            "roll": float(fields[4]),
            "left_motor": int(fields[5]),
            "right_motor": int(fields[6]),
            "armed": bool(int(fields[7])),
            "imu_online": bool(int(fields[8])),
            "orientation_valid": bool(int(fields[9])),
        }
    except ValueError:
        return None


class SerialBridge(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="esp32-serial", daemon=True)
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.port: Optional[serial.Serial] = None
        self.device: Optional[str] = None
        self.online = False
        self.error = "ESP32 not connected"
        self.latest_telemetry: Optional[dict] = None
        self.telemetry_sequence = 0
        self.last_telemetry_monotonic = 0.0
        self.latest_serial_line = ""

    def status_snapshot(self) -> dict:
        with self.state_lock:
            age_ms = None
            if self.last_telemetry_monotonic:
                age_ms = round((time.monotonic() - self.last_telemetry_monotonic) * 1000.0, 1)
            return {
                "online": self.online,
                "device": self.device,
                "error": self.error,
                "telemetry_age_ms": age_ms,
                "last_line": self.latest_serial_line,
            }

    def telemetry_snapshot(self):
        with self.state_lock:
            return self.telemetry_sequence, self.latest_telemetry

    def _set_offline(self, error: str) -> None:
        with self.state_lock:
            self.online = False
            self.error = error

    def _connect(self) -> Optional[serial.Serial]:
        devices = serial_candidates()
        if not devices:
            self._set_offline("No ESP32 serial device found")
            return None

        for device in devices:
            try:
                print(f"Trying ESP32 serial: {device}")
                port = serial.Serial(
                    port=device,
                    baudrate=SERIAL_BAUD,
                    timeout=0.1,
                    write_timeout=0.2,
                    rtscts=False,
                    dsrdtr=False,
                )
                try:
                    port.dtr = False
                    port.rts = False
                except OSError:
                    pass
                time.sleep(2.0)
                port.reset_input_buffer()
                with self.state_lock:
                    self.port = port
                    self.device = device
                    self.online = True
                    self.error = ""
                print(f"ESP32 connected: {device}")
                self.send_line("STOP")
                return port
            except (serial.SerialException, OSError) as exc:
                self._set_offline(f"{device}: {exc}")
        return None

    def send_line(self, command: str) -> bool:
        with self.write_lock:
            port = self.port
            if port is None or not port.is_open:
                return False
            try:
                port.write((command + "\n").encode("ascii"))
                port.flush()
                return True
            except (serial.SerialException, OSError) as exc:
                self._set_offline(f"Serial write failed: {exc}")
                return False

    def emergency_stop(self) -> None:
        for _ in range(2):
            self.send_line("STOP")
            time.sleep(0.01)

    def run(self) -> None:
        while not self.stop_event.is_set():
            if self.port is None or not self.port.is_open:
                port = self._connect()
                if port is None:
                    time.sleep(1.0)
                    continue
            else:
                port = self.port

            try:
                raw = port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                parsed = parse_telemetry(line)
                with self.state_lock:
                    self.latest_serial_line = line
                    if parsed is not None:
                        self.latest_telemetry = parsed
                        self.telemetry_sequence += 1
                        self.last_telemetry_monotonic = time.monotonic()
            except (serial.SerialException, OSError) as exc:
                self._set_offline(f"Serial disconnected: {exc}")
                try:
                    port.close()
                except Exception:
                    pass
                with self.state_lock:
                    self.port = None
                time.sleep(0.5)

        self.emergency_stop()
        if self.port is not None:
            try:
                self.port.close()
            except Exception:
                pass

    def stop(self) -> None:
        self.stop_event.set()


@dataclass
class ControlSession:
    armed_session: bool = False
    last_motor_command_monotonic: float = 0.0


async def control_handler(websocket, serial_bridge: SerialBridge, camera: CameraWorker, control_lock: asyncio.Lock):
    peer = websocket.remote_address
    print(f"CONTROL client connected: {peer}")

    if control_lock.locked():
        await websocket.send(json.dumps({
            "type": "error",
            "message": "Another control client is already connected",
        }))
        await websocket.close(code=1013, reason="Control client already connected")
        return

    async with control_lock:
        session = ControlSession()
        serial_bridge.emergency_stop()

        await websocket.send(json.dumps({
            "type": "hello",
            "service": "oceanova-crawler",
            "control_port": CONTROL_PORT,
            "video_port": VIDEO_PORT,
            "watchdog_ms": int(TOPSIDE_WATCHDOG_SECONDS * 1000),
        }))

        async def telemetry_sender():
            last_sequence = -1
            last_system_send = 0.0
            while True:
                sequence, telemetry = serial_bridge.telemetry_snapshot()
                if telemetry is not None and sequence != last_sequence:
                    await websocket.send(json.dumps(telemetry, separators=(",", ":")))
                    last_sequence = sequence

                now = time.monotonic()
                if now - last_system_send >= SYSTEM_STATUS_PERIOD_SECONDS:
                    camera_state = camera.snapshot()
                    serial_state = serial_bridge.status_snapshot()
                    await websocket.send(json.dumps({
                        "type": "system",
                        "esp32_online": serial_state["online"],
                        "esp32_device": serial_state["device"],
                        "telemetry_age_ms": serial_state["telemetry_age_ms"],
                        "camera_online": camera_state[2],
                        "camera_error": camera_state[3],
                        "camera_width": camera_state[5],
                        "camera_height": camera_state[6],
                        "camera_fps": camera_state[7],
                    }, separators=(",", ":")))
                    last_system_send = now
                await asyncio.sleep(0.01)

        async def command_watchdog():
            while True:
                if session.armed_session:
                    age = time.monotonic() - session.last_motor_command_monotonic
                    if age > TOPSIDE_WATCHDOG_SECONDS:
                        print("TOPSIDE COMMAND TIMEOUT -> STOP")
                        serial_bridge.emergency_stop()
                        session.armed_session = False
                        try:
                            await websocket.send(json.dumps({
                                "type": "fault",
                                "reason": "topside_command_timeout",
                            }))
                        except Exception:
                            return
                await asyncio.sleep(0.02)

        telemetry_task = asyncio.create_task(telemetry_sender())
        watchdog_task = asyncio.create_task(command_watchdog())

        try:
            async for message in websocket:
                if not isinstance(message, str):
                    continue
                try:
                    command = json.loads(message)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                msg_type = command.get("type")
                if msg_type == "ping":
                    await websocket.send(json.dumps({
                        "type": "pong",
                        "client_time": command.get("client_time"),
                        "server_time": time.time(),
                    }))
                elif msg_type == "stop":
                    serial_bridge.emergency_stop()
                    session.armed_session = False
                    await websocket.send(json.dumps({"type": "ack", "command": "stop"}))
                elif msg_type == "arm":
                    if not serial_bridge.status_snapshot()["online"]:
                        await websocket.send(json.dumps({"type": "error", "message": "ESP32 is offline"}))
                        continue
                    serial_bridge.send_line("ARM")
                    session.armed_session = True
                    session.last_motor_command_monotonic = time.monotonic()
                    await websocket.send(json.dumps({"type": "ack", "command": "arm"}))
                elif msg_type == "motor":
                    if not session.armed_session:
                        await websocket.send(json.dumps({"type": "error", "message": "Control session is not armed"}))
                        continue
                    try:
                        left = int(command["left"])
                        right = int(command["right"])
                    except (KeyError, TypeError, ValueError):
                        await websocket.send(json.dumps({"type": "error", "message": "Motor message needs integer left and right"}))
                        continue
                    left = max(-1000, min(1000, left))
                    right = max(-1000, min(1000, right))
                    serial_bridge.send_line(f"M {left} {right}")
                    session.last_motor_command_monotonic = time.monotonic()
                else:
                    await websocket.send(json.dumps({"type": "error", "message": f"Unknown command type: {msg_type}"}))
        finally:
            telemetry_task.cancel()
            watchdog_task.cancel()
            serial_bridge.emergency_stop()
            for task in (telemetry_task, watchdog_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            print(f"CONTROL client disconnected: {peer} -> STOP")


async def video_handler(websocket, camera: CameraWorker):
    peer = websocket.remote_address
    print(f"VIDEO client connected: {peer}")
    await websocket.send(json.dumps({
        "type": "video_info",
        "format": "jpeg",
        "width_requested": CAMERA_WIDTH,
        "height_requested": CAMERA_HEIGHT,
        "fps_requested": CAMERA_FPS,
    }))
    last_sequence = -1
    try:
        while True:
            sequence, jpeg, online, _error, _frame_time, _width, _height, _fps = camera.snapshot()
            if online and jpeg is not None and sequence != last_sequence:
                await websocket.send(jpeg)
                last_sequence = sequence
            else:
                await asyncio.sleep(0.005)
    finally:
        print(f"VIDEO client disconnected: {peer}")


async def async_main() -> None:
    camera = CameraWorker()
    serial_bridge = SerialBridge()
    control_lock = asyncio.Lock()
    camera.start()
    serial_bridge.start()

    stop_future = asyncio.get_running_loop().create_future()

    def request_stop():
        if not stop_future.done():
            stop_future.set_result(None)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            pass

    async def control_entry(websocket):
        await control_handler(websocket, serial_bridge, camera, control_lock)

    async def video_entry(websocket):
        await video_handler(websocket, camera)

    pi_ip = get_primary_ipv4()

    print()
    print("Oceanova crawler WebSocket bridge")
    print(f"Pi IPv4 address:      {pi_ip}")
    print(f"CONTROL + TELEMETRY: ws://{pi_ip}:{CONTROL_PORT}")
    print(f"VIDEO JPEG stream:   ws://{pi_ip}:{VIDEO_PORT}")
    print(f"Listening on:         {HOST}")
    print("Press Ctrl+C to stop.")
    print()

    try:
        async with (
            serve(control_entry, HOST, CONTROL_PORT, compression=None, ping_interval=10, ping_timeout=5),
            serve(video_entry, HOST, VIDEO_PORT, compression=None, ping_interval=10, ping_timeout=5, max_size=None),
        ):
            await stop_future
    finally:
        print("Stopping server -> STOP")
        serial_bridge.emergency_stop()
        camera.stop()
        serial_bridge.stop()
        await asyncio.to_thread(camera.join, 2.0)
        await asyncio.to_thread(serial_bridge.join, 2.0)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

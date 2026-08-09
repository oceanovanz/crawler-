#!/usr/bin/env python3
"""
Oceanova crawler Windows WebSocket viewer

Connects to the Raspberry Pi:
    ws://PI_IP:8765  control + telemetry
    ws://PI_IP:8766  video

Set PI_IP in this file before running.

This first viewer is intentionally non-driving:
    P       ping Pi
    S       STOP
    Q/Esc   STOP and quit
"""

from __future__ import annotations

import asyncio
import json
import time

import cv2
import numpy as np
from websockets.asyncio.client import connect

PI_IP = "192.168.10.2"
CONTROL_URL = f"ws://{PI_IP}:8765"
VIDEO_URL = f"ws://{PI_IP}:8766"
WINDOW_NAME = "Oceanova Crawler - Ethernet Test"


class State:
    def __init__(self) -> None:
        self.frame = None
        self.video_connected = False
        self.control_connected = False
        self.telemetry = {}
        self.system = {}
        self.rtt_ms = None
        self.control_send_queue: asyncio.Queue = asyncio.Queue()


state = State()


def draw_text(frame, text, line, colour=(255, 255, 255)):
    x = 12
    y = 28 + line * 27
    cv2.putText(frame, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, colour, 1, cv2.LINE_AA)


async def control_connection():
    while True:
        try:
            print(f"Connecting control: {CONTROL_URL}")
            async with connect(CONTROL_URL, compression=None, ping_interval=10, ping_timeout=5) as websocket:
                state.control_connected = True
                print("CONTROL connected")

                async def receiver():
                    async for message in websocket:
                        if not isinstance(message, str):
                            continue
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        msg_type = data.get("type")
                        if msg_type == "telemetry":
                            state.telemetry = data
                        elif msg_type == "system":
                            state.system = data
                        elif msg_type == "pong":
                            client_time = data.get("client_time")
                            if isinstance(client_time, (int, float)):
                                state.rtt_ms = (time.time() - float(client_time)) * 1000.0
                        elif msg_type in ("fault", "error", "ack", "hello"):
                            print("CONTROL:", data)

                async def sender():
                    while True:
                        message = await state.control_send_queue.get()
                        await websocket.send(json.dumps(message))

                recv_task = asyncio.create_task(receiver())
                send_task = asyncio.create_task(sender())
                done, pending = await asyncio.wait((recv_task, send_task), return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc is not None:
                        raise exc

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"CONTROL disconnected: {exc}")
        finally:
            state.control_connected = False
        await asyncio.sleep(1.0)


async def video_connection():
    while True:
        try:
            print(f"Connecting video: {VIDEO_URL}")
            async with connect(VIDEO_URL, compression=None, ping_interval=10, ping_timeout=5, max_size=None) as websocket:
                state.video_connected = True
                print("VIDEO connected")
                async for message in websocket:
                    if isinstance(message, str):
                        try:
                            print("VIDEO:", json.loads(message))
                        except json.JSONDecodeError:
                            pass
                        continue
                    array = np.frombuffer(message, dtype=np.uint8)
                    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
                    if frame is not None:
                        state.frame = frame
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"VIDEO disconnected: {exc}")
        finally:
            state.video_connected = False
        await asyncio.sleep(1.0)


async def request_stop():
    await state.control_send_queue.put({"type": "stop"})


async def ui_loop():
    last_auto_ping = 0.0
    while True:
        if state.frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        else:
            frame = state.frame.copy()

        telemetry = state.telemetry
        system = state.system
        draw_text(frame, f"CONTROL {'ONLINE' if state.control_connected else 'OFFLINE'}", 0,
                  (0, 255, 0) if state.control_connected else (0, 0, 255))
        draw_text(frame, f"VIDEO {'ONLINE' if state.video_connected else 'OFFLINE'}", 1,
                  (0, 255, 0) if state.video_connected else (0, 0, 255))

        if telemetry:
            draw_text(frame,
                      f"Yaw {telemetry.get('yaw', 0):.1f}  Pitch {telemetry.get('pitch', 0):.1f}  Roll {telemetry.get('roll', 0):.1f}",
                      2)
            imu_ok = telemetry.get("imu_online", False) and telemetry.get("orientation_valid", False)
            draw_text(frame, f"IMU {'VALID' if imu_ok else 'INVALID'}", 3,
                      (0, 255, 0) if imu_ok else (0, 0, 255))
            draw_text(frame,
                      f"Motors L {telemetry.get('left_motor', 0):+d} R {telemetry.get('right_motor', 0):+d} "
                      f"{'ARMED' if telemetry.get('armed') else 'DISARMED'}",
                      4)

        age = system.get("telemetry_age_ms")
        rtt_text = "--" if state.rtt_ms is None else f"{state.rtt_ms:.1f}"
        draw_text(frame, f"RTT {rtt_text} ms  Telemetry age {age if age is not None else '--'} ms", 5)
        draw_text(frame, "S STOP | P PING | Q/ESC STOP + QUIT", 6)

        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), 27):
            await request_stop()
            await asyncio.sleep(0.1)
            return
        if key == ord("s"):
            print("STOP")
            await request_stop()
        if key == ord("p"):
            await state.control_send_queue.put({"type": "ping", "client_time": time.time()})

        now = time.monotonic()
        if now - last_auto_ping >= 1.0 and state.control_connected:
            await state.control_send_queue.put({"type": "ping", "client_time": time.time()})
            last_auto_ping = now

        await asyncio.sleep(0.005)


async def async_main():
    control_task = asyncio.create_task(control_connection())
    video_task = asyncio.create_task(video_connection())
    try:
        await ui_loop()
    finally:
        await request_stop()
        control_task.cancel()
        video_task.cancel()
        for task in (control_task, video_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        cv2.destroyAllWindows()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

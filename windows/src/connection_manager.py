import cv2
import time
import json
import asyncio
import numpy as np
from pathlib import Path
from datetime import datetime
from websockets.asyncio.client import connect

from state import State
from helpers import armed, can_drive
from config import (
    CONTROL_PORT,
    VIDEO_PORT,
    RECONNECT_DELAY_S,
    COMMAND_RATE_HZ,
    UserConfiguration,
)


class ConnectionManager:
    def __init__(self, state: State, user_config: UserConfiguration, ui_events) -> None:
        self.state = state
        self.user_config = user_config
        self.ui_events = ui_events

        self.control_task: asyncio.Task | None = None
        self.video_task: asyncio.Task | None = None
        self.motor_task: asyncio.Task | None = None
        self.ping_task: asyncio.Task | None = None

        # recording
        user_config.record_dir.mkdir(parents=True, exist_ok=True)
        self.video_writer: cv2.VideoWriter | None = None
        self.recording_path: Path | None = None

        self._record_lock = asyncio.Lock()
        self._connection_lock = asyncio.Lock()

    @property
    def control_url(self) -> str:
        return f"ws://{self.user_config.pi_ip}:{CONTROL_PORT}"

    @property
    def video_url(self) -> str:
        return f"ws://{self.user_config.pi_ip}:{VIDEO_PORT}"

    @property
    def ip_connected(self) -> bool:
        return self.state.control_connected

    async def start(self) -> None:
        """Start all connection/background tasks."""
        self.control_task = asyncio.create_task(self._control_connection())
        self.video_task = asyncio.create_task(self._video_connection())
        self.motor_task = asyncio.create_task(self._motor_loop())
        self.ping_task = asyncio.create_task(self._ping_loop())

    async def stop(self) -> None:
        """Stop all connection/background tasks."""

        tasks = [self.control_task, self.video_task, self.motor_task, self.ping_task]

        for task in tasks:
            if task is not None:
                task.cancel()

        for task in tasks:
            if task is None:
                continue

            try:
                await task
            except asyncio.CancelledError:
                pass

        self.control_task = None
        self.video_task = None
        self.motor_task = None
        self.ping_task = None

        self.state.control_connected = False
        self.state.video_connected = False

    async def set_pi_ip(self, ip: str) -> None:
        """Change the crawler IP and reconnect both WebSocket connections."""

        ip = ip.strip()

        if ip == self.user_config.pi_ip:
            return

        async with self._connection_lock:
            print(f"Changing crawler IP: {self.user_config.pi_ip} -> {ip}")

            # Stop sending motors immediately.
            self.state.arm_requested = False
            self.state.throttle = 0.0
            self.state.steering = 0.0
            self.state.left = 0
            self.state.right = 0

            # Disconnect current connections.
            await self._disconnect_connections()

            # Update setting.
            self.user_config.pi_ip = ip

            # Start fresh connection tasks.
            self.control_task = asyncio.create_task(self._control_connection())
            self.video_task = asyncio.create_task(self._video_connection())

    async def take_snapshot(self) -> Path | None:
        """Save the most recent video frame as a JPEG."""

        frame = self.state.frame
        if frame is None:
            print("Cannot take snapshot: no video frame available")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = self.user_config.record_dir / f"snapshot_{timestamp}.jpg"

        success = cv2.imwrite(str(path), frame)
        if not success:
            print(f"Failed to save snapshot: {path}")
            return None

        print(f"Snapshot saved: {path}")

        return path

    async def toggle_recording(self) -> bool:
        """
        Toggle video recording.

        Returns:
            True  -> recording started
            False -> recording stopped
        """

        async with self._record_lock:

            if self.state.recording:
                self._stop_recording()
                return False

            return self._start_recording()

    def _start_recording(self) -> bool:
        """Start recording using the current video stream."""

        frame = self.state.frame

        if frame is None:
            print("Cannot start recording: no video frame available")
            return False

        height, width = frame.shape[:2]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.user_config.record_dir / f"video_{timestamp}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        writer = cv2.VideoWriter(str(path), fourcc, fps=20, frameSize=(width, height))

        if not writer.isOpened():
            print(f"Failed to open video writer: {path}")
            return False

        self.video_writer = writer
        self.state.recording = True
        self.recording_path = path

        print(f"Recording started: {path}")

        return True

    def _stop_recording(self) -> None:
        """Stop the active recording."""

        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None

        self.state.recording = False

        if self.recording_path is not None:
            print(f"Recording saved: {self.recording_path}")

        self.recording_path = None

    async def _disconnect_connections(self) -> None:
        """Cancel only the network connection tasks."""

        for task in (self.control_task, self.video_task):
            if task is not None:
                task.cancel()

        for task in (self.control_task, self.video_task):
            if task is None:
                continue

            try:
                await task
            except asyncio.CancelledError:
                pass

        self.control_task = None
        self.video_task = None

        self.state.control_connected = False
        self.state.video_connected = False
        self.state.arm_requested = False
        self.state.left = 0
        self.state.right = 0

    async def send(self, message: dict) -> None:
        await self.state.queue.put(message)

    async def stop_motors(self, reason: str) -> None:
        self.state.arm_requested = False
        self.state.throttle = 0.0
        self.state.steering = 0.0
        self.state.left = 0
        self.state.right = 0
        await self.send({"type": "stop", "reason": reason})

    async def _control_connection(self) -> None:
        while self.state.running:

            url = self.control_url

            try:
                print("Connecting control:", url)

                async with connect(url, compression=None, ping_interval=5, ping_timeout=3) as ws:

                    self.state.control_connected = True
                    self.state.arm_requested = False
                    self.state.left = self.state.right = 0

                    print("CONTROL connected")

                    async def receiver():
                        async for message in ws:

                            if not isinstance(message, str):
                                continue

                            try:
                                data = json.loads(message)
                            except json.JSONDecodeError:
                                continue

                            kind = data.get("type")

                            if kind == "telemetry":
                                self.state.telemetry = data
                                self.state.telemetry_time = time.monotonic()

                                if data.get("armed"):
                                    self.state.arm_requested = False

                            elif kind == "system":
                                self.state.system = data

                            elif kind == "pong":
                                sent = data.get("client_time")
                                if isinstance(sent, (int, float)):
                                    self.state.rtt_ms = (time.time() - float(sent)) * 1000.0

                            elif kind == "error":
                                message = data.get("message", "Unknown error")
                                self.ui_events.error.emit(message)

                            elif kind == "fault":
                                self.state.left = self.state.right = 0
                                reason = data.get("reason", "Unknown fault")
                                self.ui_events.error.emit(reason)

                            elif kind == "hello":
                                print("Hello:", data)

                            elif kind == "ack":
                                print("CONTROL:", data)

                    async def sender():
                        while self.state.running:
                            message = await self.state.queue.get()
                            await ws.send(json.dumps(message, separators=(",", ":")))

                    receiver_task = asyncio.create_task(receiver())
                    sender_task = asyncio.create_task(sender())

                    done, pending = await asyncio.wait(
                        (receiver_task, sender_task),
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()

                    for task in pending:
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    for task in done:
                        exc = task.exception()
                        if exc:
                            raise exc

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                print("CONTROL disconnected:", exc)

            finally:
                self.state.control_connected = False
                self.state.arm_requested = False
                self.state.left = self.state.right = 0

            if self.state.running:
                await asyncio.sleep(RECONNECT_DELAY_S)

    async def _video_connection(self) -> None:
        while self.state.running:

            url = self.video_url

            try:
                print("Connecting video:", url)

                async with connect(
                    url,
                    compression=None,
                    ping_interval=5,
                    ping_timeout=3,
                    max_size=None,
                ) as ws:

                    self.state.video_connected = True
                    print("VIDEO connected")

                    async for message in ws:

                        if isinstance(message, str):
                            continue

                        frame = cv2.imdecode(np.frombuffer(message, dtype=np.uint8), cv2.IMREAD_COLOR)

                        if frame is None:
                            continue

                        self.state.frame = frame

                        if self.state.recording and self.video_writer is not None:
                            self.video_writer.write(frame)

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                print("VIDEO disconnected:", exc)

            finally:
                self.state.video_connected = False
                if self.state.recording:
                    print("Video connection lost - stopping recording")
                    self._stop_recording()

            if self.state.running:
                await asyncio.sleep(RECONNECT_DELAY_S)

    async def _motor_loop(self) -> None:
        period = 1.0 / COMMAND_RATE_HZ

        while self.state.running:

            t0 = time.monotonic()

            if self.state.control_connected and armed(self.state):
                left = self.state.left if can_drive() else 0
                right = self.state.right if can_drive() else 0

                await self.send({"type": "motor", "left": left, "right": right})

            await asyncio.sleep(max(0.0, period - (time.monotonic() - t0)))

    async def _ping_loop(self) -> None:
        while self.state.running:

            if self.state.control_connected:
                await self.send({"type": "ping", "client_time": time.time()})

            await asyncio.sleep(1.0)

#!/usr/bin/env python3
"""Oceanova crawler Windows topside control station.

Current controls:
  OPTIONS / START  arm
  CIRCLE           immediate STOP + disarm
  left stick Y     forward / reverse
  right stick X    skid steering
  S                STOP + disarm
  P                ping Pi
  Q / ESC          STOP + quit

There is intentionally no hold-to-run deadman in this version. Once armed,
valid stick input can command the crawler. The full ESP32 command range of
-1000..+1000 is used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
import pygame
from pygame._sdl2 import controller as sdl2_controller
from websockets.asyncio.client import connect

DEFAULT_PI_IP = "192.168.88.5"
CONTROL_PORT = 8765
VIDEO_PORT = 8766
MAX_MOTOR_COMMAND = 1000
GAMEPAD_DEADZONE = 0.12
COMMAND_RATE_HZ = 20.0
TELEMETRY_OFFLINE_MS = 1000
RECONNECT_DELAY_S = 1.0

THROTTLE_SIGN = 1.0
STEERING_SIGN = 1.0

WINDOW_TITLE = "Oceanova Crawler"
WINDOW_SIZE = (1280, 720)

BG = (12, 17, 22)
PANEL = (22, 30, 38)
TEXT = (230, 237, 242)
MUTED = (145, 159, 170)
GOOD = (88, 214, 141)
WARN = (244, 190, 76)
BAD = (245, 91, 91)
BLUE = (101, 185, 231)


@dataclass
class State:
    running: bool = True
    control_connected: bool = False
    video_connected: bool = False
    controller_connected: bool = False
    telemetry: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    frame: Optional[np.ndarray] = None
    telemetry_time: float = 0.0
    rtt_ms: Optional[float] = None
    arm_requested: bool = False
    throttle: float = 0.0
    steering: float = 0.0
    left: int = 0
    right: int = 0
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


state = State()


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def deadzone(v: float) -> float:
    if abs(v) <= GAMEPAD_DEADZONE:
        return 0.0
    mag = (abs(v) - GAMEPAD_DEADZONE) / (1.0 - GAMEPAD_DEADZONE)
    return math.copysign(mag, v)


def telemetry_age_ms() -> Optional[float]:
    if not state.telemetry_time:
        return None
    return (time.monotonic() - state.telemetry_time) * 1000.0


def armed() -> bool:
    return bool(state.telemetry.get("armed", False))


def telemetry_fresh() -> bool:
    age = telemetry_age_ms()
    return age is not None and age < TELEMETRY_OFFLINE_MS


def can_drive() -> bool:
    return (
        state.control_connected
        and state.controller_connected
        and telemetry_fresh()
        and armed()
    )


def mix(throttle: float, steering: float) -> tuple[int, int]:
    left = throttle + steering
    right = throttle - steering
    peak = max(1.0, abs(left), abs(right))
    return (
        int(round((left / peak) * MAX_MOTOR_COMMAND)),
        int(round((right / peak) * MAX_MOTOR_COMMAND)),
    )


async def send(message: dict) -> None:
    await state.queue.put(message)


async def stop(reason: str) -> None:
    state.arm_requested = False
    state.throttle = state.steering = 0.0
    state.left = state.right = 0
    await send({"type": "stop", "reason": reason})


class DualSense:
    def __init__(self) -> None:
        self.pad = None
        self.prev_options = False
        self.prev_circle = False

    def start(self) -> None:
        pygame.init()
        pygame.joystick.init()
        sdl2_controller.init()
        self.scan()

    def scan(self) -> None:
        if self.pad is not None:
            try:
                if self.pad.attached():
                    state.controller_connected = True
                    return
            except pygame.error:
                pass
            try:
                self.pad.quit()
            except pygame.error:
                pass
            self.pad = None

        state.controller_connected = False
        for i in range(sdl2_controller.get_count()):
            try:
                if not sdl2_controller.is_controller(i):
                    continue
                self.pad = sdl2_controller.Controller(i)
                state.controller_connected = True
                print("Controller connected:", sdl2_controller.name_forindex(i))
                return
            except pygame.error:
                pass

    def axis(self, axis_id: int) -> float:
        if self.pad is None:
            return 0.0
        try:
            return clamp(self.pad.get_axis(axis_id) / 32767.0, -1.0, 1.0)
        except pygame.error:
            return 0.0

    def button(self, button_id: int) -> bool:
        if self.pad is None:
            return False
        try:
            return bool(self.pad.get_button(button_id))
        except pygame.error:
            return False

    async def update(self) -> None:
        self.scan()
        if self.pad is None:
            state.throttle = state.steering = 0.0
            state.left = state.right = 0
            return

        try:
            if not self.pad.attached():
                state.controller_connected = False
                await stop("CONTROLLER DISCONNECTED")
                self.pad = None
                return
        except pygame.error:
            await stop("CONTROLLER ERROR")
            self.pad = None
            return

        options = self.button(pygame.CONTROLLER_BUTTON_START)
        circle = self.button(pygame.CONTROLLER_BUTTON_B)

        if options and not self.prev_options:
            if state.control_connected and telemetry_fresh() and not armed():
                state.arm_requested = True
                print("ARM requested")
                await send({"type": "arm"})

        if circle and not self.prev_circle:
            print("CIRCLE -> STOP")
            await stop("OPERATOR CIRCLE")

        self.prev_options = options
        self.prev_circle = circle

        state.throttle = clamp(
            deadzone(-self.axis(pygame.CONTROLLER_AXIS_LEFTY)) * THROTTLE_SIGN,
            -1.0,
            1.0,
        )
        state.steering = clamp(
            deadzone(self.axis(pygame.CONTROLLER_AXIS_RIGHTX)) * STEERING_SIGN,
            -1.0,
            1.0,
        )

        if can_drive():
            state.left, state.right = mix(state.throttle, state.steering)
        else:
            state.left = state.right = 0

    def close(self) -> None:
        if self.pad is not None:
            try:
                self.pad.quit()
            except pygame.error:
                pass
        sdl2_controller.quit()


async def control_connection(url: str) -> None:
    while state.running:
        try:
            print("Connecting control:", url)
            async with connect(url, compression=None, ping_interval=5, ping_timeout=3) as ws:
                state.control_connected = True
                state.arm_requested = False
                state.left = state.right = 0
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
                            state.telemetry = data
                            state.telemetry_time = time.monotonic()
                            if data.get("armed"):
                                state.arm_requested = False
                        elif kind == "system":
                            state.system = data
                        elif kind == "pong":
                            sent = data.get("client_time")
                            if isinstance(sent, (int, float)):
                                state.rtt_ms = (time.time() - float(sent)) * 1000.0
                        elif kind in ("fault", "error", "ack", "hello"):
                            print("CONTROL:", data)
                            if kind == "fault":
                                state.left = state.right = 0

                async def sender():
                    while state.running:
                        await ws.send(json.dumps(await state.queue.get(), separators=(",", ":")))

                r = asyncio.create_task(receiver())
                s = asyncio.create_task(sender())
                done, pending = await asyncio.wait((r, s), return_when=asyncio.FIRST_COMPLETED)
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
            state.control_connected = False
            state.arm_requested = False
            state.left = state.right = 0
        if state.running:
            await asyncio.sleep(RECONNECT_DELAY_S)


async def video_connection(url: str) -> None:
    while state.running:
        try:
            print("Connecting video:", url)
            async with connect(url, compression=None, ping_interval=5, ping_timeout=3, max_size=None) as ws:
                state.video_connected = True
                print("VIDEO connected")
                async for message in ws:
                    if isinstance(message, str):
                        continue
                    frame = cv2.imdecode(np.frombuffer(message, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        state.frame = frame
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("VIDEO disconnected:", exc)
        finally:
            state.video_connected = False
        if state.running:
            await asyncio.sleep(RECONNECT_DELAY_S)


async def motor_loop() -> None:
    period = 1.0 / COMMAND_RATE_HZ
    while state.running:
        t0 = time.monotonic()
        if state.control_connected and armed():
            left = state.left if can_drive() else 0
            right = state.right if can_drive() else 0
            await send({"type": "motor", "left": left, "right": right})
        await asyncio.sleep(max(0.0, period - (time.monotonic() - t0)))


async def ping_loop() -> None:
    while state.running:
        if state.control_connected:
            await send({"type": "ping", "client_time": time.time()})
        await asyncio.sleep(1.0)


def text(surface, font, value, xy, colour=TEXT):
    surface.blit(font.render(value, True, colour), xy)


def camera_surface(frame: np.ndarray) -> pygame.Surface:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")


async def ui(pad: DualSense) -> None:
    screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
    pygame.display.set_caption(WINDOW_TITLE)
    small = pygame.font.SysFont("Segoe UI", 18)
    medium = pygame.font.SysFont("Segoe UI", 22, bold=True)
    large = pygame.font.SysFont("Segoe UI", 32, bold=True)
    clock = pygame.time.Clock()
    had_focus = True

    while state.running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                await stop("WINDOW CLOSED")
                state.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    await stop("KEYBOARD QUIT")
                    state.running = False
                elif event.key == pygame.K_s:
                    await stop("KEYBOARD STOP")
                elif event.key == pygame.K_p:
                    await send({"type": "ping", "client_time": time.time()})

        if not state.running:
            break

        focused = bool(pygame.key.get_focused())
        if had_focus and not focused:
            await stop("WINDOW FOCUS LOST")
        had_focus = focused

        await pad.update()

        age = telemetry_age_ms()
        if armed() and age is not None and age >= TELEMETRY_OFFLINE_MS:
            await stop("TELEMETRY TIMEOUT")

        width, height = screen.get_size()
        top_h = 48
        side_w = max(310, int(width * 0.25))
        bottom_h = 105
        video_rect = pygame.Rect(0, top_h, width - side_w, height - top_h - bottom_h)
        side_rect = pygame.Rect(width - side_w, top_h, side_w, height - top_h)

        screen.fill(BG)
        pygame.draw.rect(screen, PANEL, (0, 0, width, top_h))
        pygame.draw.rect(screen, PANEL, side_rect)
        pygame.draw.rect(screen, (0, 0, 0), video_rect)

        text(screen, medium, "OCEANOVA CRAWLER", (16, 12), BLUE)
        status = (
            f"LINK {'●' if state.control_connected else '○'}   "
            f"VIDEO {'●' if state.video_connected else '○'}   "
            f"DUALSENSE {'●' if state.controller_connected else '○'}"
        )
        text(screen, small, status, (245, 15), GOOD if state.control_connected else BAD)

        arm_label = "ARMED - FULL PWM" if armed() else ("ARM REQUESTED" if state.arm_requested else "DISARMED")
        arm_colour = WARN if armed() or state.arm_requested else GOOD
        arm_surface = medium.render(arm_label, True, arm_colour)
        screen.blit(arm_surface, (width - arm_surface.get_width() - 18, 12))

        if state.frame is not None:
            surf = camera_surface(state.frame)
            sw, sh = surf.get_size()
            scale = min(video_rect.width / sw, video_rect.height / sh)
            surf = pygame.transform.smoothscale(surf, (int(sw * scale), int(sh * scale)))
            screen.blit(surf, surf.get_rect(center=video_rect.center))
        else:
            wait = medium.render("WAITING FOR CRAWLER VIDEO", True, MUTED)
            screen.blit(wait, wait.get_rect(center=video_rect.center))

        sx = side_rect.x + 22
        y = top_h + 22
        text(screen, small, "HEADING", (sx, y), MUTED)
        y += 30
        yaw = state.telemetry.get("yaw")
        text(screen, large, "---.-°" if yaw is None else f"{yaw:05.1f}°", (sx, y))
        y += 64
        pitch = state.telemetry.get("pitch")
        roll = state.telemetry.get("roll")
        text(screen, medium, f"Pitch   {pitch if pitch is not None else '--'}°", (sx, y)); y += 34
        text(screen, medium, f"Roll    {roll if roll is not None else '--'}°", (sx, y)); y += 54
        text(screen, small, f"Throttle  {state.throttle:+.2f}", (sx, y)); y += 28
        text(screen, small, f"Steering  {state.steering:+.2f}", (sx, y)); y += 38
        text(screen, small, "NO DEADMAN - ARMED STICKS LIVE", (sx, y), WARN); y += 40
        text(screen, small, "Motor limit: 1000 / 1000", (sx, y), MUTED); y += 28
        text(screen, small, f"L command: {state.telemetry.get('left_motor', 0):+d}", (sx, y)); y += 28
        text(screen, small, f"R command: {state.telemetry.get('right_motor', 0):+d}", (sx, y)); y += 28
        age_text = "--" if age is None else f"{age:.0f} ms"
        rtt_text = "--" if state.rtt_ms is None else f"{state.rtt_ms:.1f} ms"
        text(screen, small, f"Telemetry: {age_text}", (sx, y), MUTED); y += 28
        text(screen, small, f"RTT: {rtt_text}", (sx, y), MUTED)

        pygame.draw.rect(screen, PANEL, (0, height - bottom_h, width - side_w, bottom_h))
        text(screen, small, "OPTIONS = ARM   |   CIRCLE / S = STOP   |   ESC / Q = STOP + QUIT", (20, height - 70))
        text(screen, small, "Left stick = throttle   |   Right stick = steering", (20, height - 38), MUTED)

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)


async def run(pi_ip: str) -> None:
    control_url = f"ws://{pi_ip}:{CONTROL_PORT}"
    video_url = f"ws://{pi_ip}:{VIDEO_PORT}"

    pad = DualSense()
    pad.start()

    print(f"Pi: {pi_ip}")
    print(f"Control: {control_url}")
    print(f"Video: {video_url}")
    print("Motor range: -1000..+1000 (full PWM request)")
    print("No deadman switch; once armed the sticks are live.")

    tasks = [
        asyncio.create_task(control_connection(control_url)),
        asyncio.create_task(video_connection(video_url)),
        asyncio.create_task(motor_loop()),
        asyncio.create_task(ping_loop()),
    ]

    try:
        await ui(pad)
    finally:
        state.running = False
        try:
            await stop("TOPSIDE SHUTDOWN")
            await asyncio.sleep(0.15)
        except Exception:
            pass
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        pad.close()
        pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pi", default=DEFAULT_PI_IP, help="crawler Raspberry Pi IPv4 address")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.pi))
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()

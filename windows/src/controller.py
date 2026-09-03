import pygame
from pygame._sdl2 import controller as sdl2_controller

from state import State
from connection_manager import ConnectionManager

from config import (
    THROTTLE_SIGN,
    STEERING_SIGN,
)

from helpers import clamp, deadzone, can_drive, mix, telemetry_fresh, armed


class DualSense:

    def __init__(self, connection: ConnectionManager, state: State) -> None:
        self.state = state
        self.connection = connection

        self.pad = None

        self.prev_options = False
        self.prev_circle = False

    def start(self) -> None:
        pygame.init()
        pygame.joystick.init()
        sdl2_controller.init()

        if not sdl2_controller.init():
            print("Failed to initialise SDL2 controller subsystem")
            return

        print("SDL controllers:", sdl2_controller.get_count())

        self.scan()

    def scan(self) -> None:
        pygame.event.pump()

        if self.pad is not None:

            try:
                if self.pad.attached():
                    self.state.controller_connected = True
                    return
            except pygame.error:
                pass

            try:
                self.pad.quit()
            except pygame.error:
                pass

            self.pad = None

        self.state.controller_connected = False

        for i in range(sdl2_controller.get_count()):
            try:

                if not sdl2_controller.is_controller(i):
                    continue

                self.pad = sdl2_controller.Controller(i)
                self.state.controller_connected = True

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
            self.state.throttle = 0.0
            self.state.steering = 0.0
            self.state.left = 0
            self.state.right = 0
            return

        # Check controller attachment
        try:
            if not self.pad.attached():
                self.state.controller_connected = False
                await self.connection.stop_motors("CONTROLLER DISCONNECTED")
                self.pad = None
                return

        except pygame.error:
            await self.connection.stop_motors("CONTROLLER ERROR")
            self.pad = None
            return

        # Buttons
        options = self.button(pygame.CONTROLLER_BUTTON_START)
        circle = self.button(pygame.CONTROLLER_BUTTON_B)

        # ARM
        if options and not self.prev_options:
            if (
                self.state.control_connected
                and telemetry_fresh(self.state)
                and not armed(self.state)
            ):
                self.state.arm_requested = True
                print("ARM requested")
                await self.connection.send({"type": "arm"})

        # STOP
        if circle and not self.prev_circle:
            print("CIRCLE -> STOP")
            await self.connection.stop_motors("OPERATOR CIRCLE")

        self.prev_options = options
        self.prev_circle = circle

        # Sticks
        self.state.throttle = clamp(
            deadzone(-self.axis(pygame.CONTROLLER_AXIS_LEFTY)) * THROTTLE_SIGN,
            -1.0,
            1.0,
        )

        self.state.steering = clamp(
            deadzone(self.axis(pygame.CONTROLLER_AXIS_RIGHTX)) * STEERING_SIGN,
            -1.0,
            1.0,
        )

        # Motor mixing
        if can_drive(self.state):
            self.state.left, self.state.right = mix(
                self.state.throttle, self.state.steering
            )
        else:
            self.state.left = 0
            self.state.right = 0

    def close(self) -> None:
        if self.pad is not None:
            try:
                self.pad.quit()
            except pygame.error:
                pass

        self.state.controller_connected = False
        sdl2_controller.quit()

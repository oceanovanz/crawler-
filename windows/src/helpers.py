import sys
import math
import time
from typing import Optional
from pathlib import Path

from state import State
from config import GAMEPAD_DEADZONE, MAX_MOTOR_COMMAND, TELEMETRY_OFFLINE_MS


def resource_path(relative_path: str) -> Path:
    """Gets the windows project directory"""
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent

    return base_path / relative_path


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def deadzone(v: float) -> float:
    if abs(v) <= GAMEPAD_DEADZONE:
        return 0.0

    mag = (abs(v) - GAMEPAD_DEADZONE) / (1.0 - GAMEPAD_DEADZONE)

    return math.copysign(mag, v)


def telemetry_age_ms(state: State) -> Optional[float]:
    if not state.telemetry_time:
        return None

    return (time.monotonic() - state.telemetry_time) * 1000.0


def armed(state: State) -> bool:
    return bool(state.telemetry.get("armed", False))


def telemetry_fresh(state: State) -> bool:
    age = telemetry_age_ms(state)

    return age is not None and age < TELEMETRY_OFFLINE_MS


def can_drive(state: State) -> bool:
    return (
        state.control_connected
        and state.controller_connected
        and telemetry_fresh(state)
        and armed(state)
    )


def mix(throttle: float, steering: float) -> tuple[int, int]:
    left = throttle + steering
    right = throttle - steering
    peak = max(1.0, abs(left), abs(right))

    return (
        int(round((left / peak) * MAX_MOTOR_COMMAND)),
        int(round((right / peak) * MAX_MOTOR_COMMAND)),
    )

import math
import time
from typing import Optional

from state import State
from config import GAMEPAD_DEADZONE, MAX_MOTOR_COMMAND, TELEMETRY_OFFLINE_MS


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


def get_mode(state: State) -> str:
    try:
        return state.system["mode"]
    except:
        return "unknown"


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

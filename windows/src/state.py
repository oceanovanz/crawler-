import asyncio
import time
import numpy as np
from typing import Optional
from dataclasses import dataclass, field

from config import TELEMETRY_OFFLINE_MS


@dataclass
class State:
    # Application
    running: bool = True

    # Recording status
    recording: bool = False

    # Connection state
    control_connected: bool = False
    video_connected: bool = False
    controller_connected: bool = False

    # Crawler state
    map_uploaded: bool = False
    route_uploaded: bool = False
    telemetry: dict = field(default_factory=dict)
    pose: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    map: dict = field(default_factory=dict)
    has_new_map: bool = False
    frame: Optional[np.ndarray] = None
    rtt_ms: Optional[float] = None

    # Operator / motor state
    arm_requested: bool = False
    throttle: float = 0.0
    steering: float = 0.0
    left: int = 0
    right: int = 0

    # Outgoing control messages
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    def wipe_telemetry(self):
        self.telemetry = {}

    def is_armed(self) -> bool:
        try:
            return bool(self.telemetry["motor"]["armed"])
        except:
            return False

    def get_mode(self) -> str:
        try:
            return self.system["mode"]
        except:
            return "unknown"

    def is_telemetry_fresh(self) -> bool:
        age = self.system.get("telemetry_age_ms", None)
        return age is not None and age < TELEMETRY_OFFLINE_MS

    def can_drive(self) -> bool:
        return self.control_connected and self.controller_connected and self.is_telemetry_fresh() and self.is_armed()

import asyncio
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

    # Navigational state
    map_uploaded: bool = False
    route_uploaded: bool = False
    route: list = field(default_factory=list)  # List of waypoints, each waypoint is a tuple (x, y, yaw)
    has_new_map: bool = False  # True if a new map has been received from the robot since the last upload
    map: dict = field(default_factory=dict)  # The ROS2 map representation, as received from the robot
    pose: dict = field(default_factory=dict)  # The ROS2 estimated  robot pose

    # Crawler state
    telemetry: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
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

    def can_drive_manual(self) -> bool:
        return (
            self.get_mode() == "manual"
            and self.control_connected
            and self.controller_connected
            and self.is_telemetry_fresh()
            and self.is_armed()
        )

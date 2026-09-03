import asyncio
import numpy as np
from typing import Optional
from dataclasses import dataclass, field


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
    telemetry: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    frame: Optional[np.ndarray] = None
    telemetry_time: float = 0.0
    rtt_ms: Optional[float] = None

    # Operator / motor state
    arm_requested: bool = False
    throttle: float = 0.0
    steering: float = 0.0
    left: int = 0
    right: int = 0

    # Planning state
    has_coverage_plan: bool = False
    coverage_plan: dict = field(default_factory=dict)

    # Outgoing control messages
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

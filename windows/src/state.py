from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import asyncio
import numpy as np

from config import DEFAULT_PI_IP, DEFAULT_RECORD_DIR


@dataclass
class State:
    # Application
    running: bool = True

    # Connection configuration
    pi_ip: str = DEFAULT_PI_IP

    # Recording status
    recording: bool = False
    record_dir: Path = field(default_factory=lambda: DEFAULT_RECORD_DIR)

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

    # Outgoing control messages
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

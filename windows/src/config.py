import json
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field

# --- Default configuration ---
DEFAULT_PI_IP = "192.168.88.5"
DEFAULT_RECORD_DIR = Path.home() / "OceanovaCrawler" / "recordings"

# --- Application constants ---
CONTROL_PORT = 8765
VIDEO_PORT = 8766

MAX_MOTOR_COMMAND = 1000
GAMEPAD_DEADZONE = 0.12
COMMAND_RATE_HZ = 20.0
TELEMETRY_OFFLINE_MS = 1000
RECONNECT_DELAY_S = 1.0

THROTTLE_SIGN = 1.0
STEERING_SIGN = 1.0

# --- User configuration ---
CONFIG_DIR = Path.home() / "OceanovaCrawler"
USER_CONFIG_FILE = CONFIG_DIR / "user_configuration.json"

DEFAULT_BOUNDARY_WIDTH = 0.0
DEFAULT_BOUNDARY_LENGTH = 0.0

DEFAULT_PATH_TYPE = "REEDS_SHEPP"
DEFAULT_ROUTE_TYPE = "BOUSTROPHEDON"
DEFAULT_HEADLAND_WIDTH = 0.0
DEFAULT_SWATH_OBJECTIVE = "LENGTH"
DEFAULT_SWATH_MODE = "BRUTE_FORCE"


@dataclass
class BoundaryConfiguration:
    width: float = DEFAULT_BOUNDARY_WIDTH
    length: float = DEFAULT_BOUNDARY_LENGTH


@dataclass
class NavigationConfiguration:
    path_type: str = DEFAULT_PATH_TYPE
    route_type: str = DEFAULT_ROUTE_TYPE
    headland_width: float = DEFAULT_HEADLAND_WIDTH
    swath_objective: str = DEFAULT_SWATH_OBJECTIVE
    swath_mode: str = DEFAULT_SWATH_MODE


@dataclass
class UserConfiguration:
    pi_ip: str = DEFAULT_PI_IP
    record_dir: Path = DEFAULT_RECORD_DIR

    boundary: BoundaryConfiguration = field(default_factory=BoundaryConfiguration)
    navigation: NavigationConfiguration = field(default_factory=NavigationConfiguration)
    current_pose: np.ndarray = field(default_factory=lambda: np.array([np.nan, np.nan, np.nan], dtype=float))

    has_coverage_plan: bool = False
    coverage_plan: dict = field(default_factory=dict)

    def has_pose(self) -> bool:
        pose = self.current_pose
        return isinstance(pose, np.ndarray) and pose.shape == (3,) and np.all(np.isfinite(pose))

    def pose_msg(self) -> str:
        x, y, yaw = self.current_pose
        return {"type": "current_pose", "pose": {"x": x, "y": y, "yaw": yaw}}

    def plan_msg(self) -> str:
        return {
            "type": "plan",
            "boundary": {
                "width": self.boundary.width,
                "length": self.boundary.length,
            },
            "navigation": {
                "path_type": self.navigation.path_type,
                "route_type": self.navigation.route_type,
                "headland_width": self.navigation.headland_width,
                "swath_objective": self.navigation.swath_objective,
                "swath_mode": self.navigation.swath_mode,
            },
        }


def load_user_config() -> UserConfiguration:
    config = UserConfiguration()

    if not USER_CONFIG_FILE.exists():
        return config

    try:
        with USER_CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Connection
        if "pi_ip" in data:
            config.pi_ip = str(data["pi_ip"])

        # Recording
        if "record_dir" in data:
            config.record_dir = Path(data["record_dir"])

        # Boundary
        boundary = data.get("boundary", {})
        if "width" in boundary:
            config.boundary.width = float(boundary["width"])
        if "length" in boundary:
            config.boundary.length = float(boundary["length"])

        # Path planning
        navigation = data.get("navigation", {})
        if "path_type" in navigation:
            config.navigation.path_type = str(navigation["path_type"])
        if "route_type" in navigation:
            config.navigation.route_type = str(navigation["route_type"])
        if "headland_width" in navigation:
            config.navigation.headland_width = float(navigation["headland_width"])
        if "swath_objective" in navigation:
            config.navigation.swath_objective = str(navigation["swath_objective"])
        if "swath_mode" in navigation:
            config.navigation.swath_mode = str(navigation["swath_mode"])
        if "has_coverage_plan" in navigation:
            config.has_coverage_plan = bool(navigation["has_coverage_plan"])
        if "coverage_plan" in navigation:
            config.coverage_plan = dict(navigation["coverage_plan"])

    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"Failed to load user configuration: {exc}")

    return config


def save_user_config(config: UserConfiguration) -> bool:

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "pi_ip": config.pi_ip,
            "record_dir": str(config.record_dir),
            "boundary": {
                "width": config.boundary.width,
                "length": config.boundary.length,
            },
            "navigation": {
                "path_type": config.navigation.path_type,
                "route_type": config.navigation.route_type,
                "headland_width": config.navigation.headland_width,
                "swath_objective": config.navigation.swath_objective,
                "swath_mode": config.navigation.swath_mode,
                "has_coverage_plan": config.has_coverage_plan,
                "coverage_plan": config.coverage_plan,
            },
        }

        # Write to a temporary file first so that an interrupted write doesn't leave corrupt config.
        temp_file = USER_CONFIG_FILE.with_suffix(".tmp")

        with temp_file.open(
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(data, f, indent=4)
            f.write("\n")

        temp_file.replace(USER_CONFIG_FILE)

        print(f"User configuration saved: " f"{USER_CONFIG_FILE}")

        return True

    except OSError as exc:
        print(f"Failed to save user configuration: {exc}")
        return False

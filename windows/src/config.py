import json
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

DEFAULT_BOUNDARY_WIDTH = 10.0
DEFAULT_BOUNDARY_LENGTH = 20.0

DEFAULT_ROBOT_WIDTH = 0.5
DEFAULT_VACUUM_WIDTH = 0.5
DEFAULT_MIN_TURNING_RADIUS = 1.0
DEFAULT_LINEAR_CURVATURE_CHANGE = 1.0

DEFAULT_PATH_TYPE = "DUBIN"
DEFAULT_ROUTE_TYPE = "BOUSTROPHEDON"


@dataclass
class BoundaryConfiguration:
    width: float = DEFAULT_BOUNDARY_WIDTH
    length: float = DEFAULT_BOUNDARY_LENGTH


@dataclass
class ROVConfiguration:
    robot_width: float = DEFAULT_ROBOT_WIDTH
    vacuum_width: float = DEFAULT_VACUUM_WIDTH
    min_turning_radius: float = DEFAULT_MIN_TURNING_RADIUS
    linear_curvature_change: float = DEFAULT_LINEAR_CURVATURE_CHANGE


@dataclass
class PathPlanningConfiguration:
    path_type: str = DEFAULT_PATH_TYPE
    route_type: str = DEFAULT_ROUTE_TYPE


@dataclass
class UserConfiguration:
    pi_ip: str = DEFAULT_PI_IP
    record_dir: Path = DEFAULT_RECORD_DIR

    boundary: BoundaryConfiguration = field(default_factory=BoundaryConfiguration)
    rov: ROVConfiguration = field(default_factory=ROVConfiguration)
    path_planning: PathPlanningConfiguration = field(
        default_factory=PathPlanningConfiguration
    )


def load_user_config() -> UserConfiguration:
    config = UserConfiguration()

    if not USER_CONFIG_FILE.exists():
        return config

    try:
        with USER_CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        #
        # Connection
        if "pi_ip" in data:
            config.pi_ip = str(data["pi_ip"])

        if "record_dir" in data:
            config.record_dir = Path(data["record_dir"])

        # Boundary
        boundary = data.get("boundary", {})
        if "width" in boundary:
            config.boundary.width = float(boundary["width"])
        if "length" in boundary:
            config.boundary.length = float(boundary["length"])

        # ROV
        rov = data.get("rov", {})

        if "robot_width" in rov:
            config.rov.robot_width = float(rov["robot_width"])

        if "vacuum_width" in rov:
            config.rov.vacuum_width = float(rov["vacuum_width"])

        if "min_turning_radius" in rov:
            config.rov.min_turning_radius = float(rov["min_turning_radius"])

        if "linear_curvature_change" in rov:
            config.rov.linear_curvature_change = float(rov["linear_curvature_change"])

        # Path planning
        path_planning = data.get("path_planning", {})

        if "path_type" in path_planning:
            config.path_planning.path_type = str(path_planning["path_type"])

        if "route_type" in path_planning:
            config.path_planning.route_type = str(path_planning["route_type"])

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
            "rov": {
                "robot_width": config.rov.robot_width,
                "vacuum_width": config.rov.vacuum_width,
                "min_turning_radius": config.rov.min_turning_radius,
                "linear_curvature_change": (config.rov.linear_curvature_change),
            },
            "path_planning": {
                "path_type": config.path_planning.path_type,
                "route_type": config.path_planning.route_type,
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

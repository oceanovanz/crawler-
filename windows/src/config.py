import json
from pathlib import Path
from dataclasses import dataclass

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


@dataclass
class UserConfiguration:
    pi_ip: str = DEFAULT_PI_IP
    record_dir: Path = DEFAULT_RECORD_DIR


def load_user_config() -> UserConfiguration:
    config = UserConfiguration()

    if not USER_CONFIG_FILE.exists():
        return config

    try:
        with USER_CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if "pi_ip" in data:
            config.pi_ip = str(data["pi_ip"])

        if "record_dir" in data:
            config.record_dir = Path(data["record_dir"])

    except (OSError, json.JSONDecodeError) as exc:
        print(f"Failed to load user configuration: {exc}")

    return config


def save_user_config(pi_ip: str, record_dir: Path) -> bool:

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        config = {"pi_ip": pi_ip, "record_dir": str(record_dir)}

        # Write to a temp file first -> avoids leaving partial config if app closes
        temp_file = USER_CONFIG_FILE.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
            f.write("\n")
        temp_file.replace(USER_CONFIG_FILE)

        print(f"User configuration saved: " f"{USER_CONFIG_FILE}")

        return True

    except OSError as exc:
        print(f"Failed to save user configuration: {exc}")
        return False

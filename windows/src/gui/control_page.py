from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from state import State
from connection_manager import ConnectionManager
from helpers import armed, telemetry_age_ms

from .video_widget import VideoWidget

TEXT_STYLE = "color: white;"
WARNING_STYLE = "color: #f4be4c; font-weight: bold;"
ERROR_STYLE = "color: #f55b5b; font-weight: bold;"


class ControlPage(QWidget):

    settings_requested = Signal()
    planning_requested = Signal()

    def __init__(
        self, state: State, connection: ConnectionManager, parent=None
    ) -> None:
        super().__init__(parent)

        self.state = state
        self.connection = connection

        # --- Top bar ---
        top_bar = QWidget()
        top_bar.setObjectName("topBar")

        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 0, 10, 0)
        top_layout.setSpacing(10)

        title = QLabel("OCEANOVA CRAWLER")
        title.setObjectName("title")

        self.control_status = QLabel()
        self.video_status = QLabel()
        self.controller_status = QLabel()

        self.update_connection_status()

        # Planning Button
        self.route_button = QPushButton("📋")
        self.route_button.setFixedSize(34, 34)
        self.route_button.setToolTip("Planning")
        self.route_button.setStyleSheet("font-size: 18px;")
        self.route_button.clicked.connect(self.planning_requested.emit)

        # Settings Button
        self.gear_button = QPushButton("⚙")
        self.gear_button.setFixedSize(34, 34)
        self.gear_button.setToolTip("Settings")
        self.gear_button.setStyleSheet(
            "color: white; font-size: 18px; font-weight: bold;"
        )
        self.gear_button.clicked.connect(self.settings_requested.emit)

        top_layout.addWidget(title)
        top_layout.addSpacing(20)

        top_layout.addWidget(self.control_status)
        top_layout.addWidget(self.video_status)
        top_layout.addWidget(self.controller_status)

        top_layout.addStretch()

        top_layout.addWidget(self.route_button)
        top_layout.addWidget(self.gear_button)

        # --- Video ---
        self.video = VideoWidget(state, connection)

        # --- Right panel ---
        self.arm_label = QLabel()

        self.yaw_label = QLabel()
        self.pitch_label = QLabel()
        self.roll_label = QLabel()
        self.throttle_label = QLabel()
        self.steering_label = QLabel()

        self.warning_label = QLabel("NO DEADMAN - ARMED STICKS LIVE")
        self.warning_label.setStyleSheet(WARNING_STYLE)

        self.motor_limit_label = QLabel("Motor limit: 1000 / 1000")
        self.left_motor_label = QLabel()
        self.right_motor_label = QLabel()

        self.ultrasonic_label = QLabel()

        self.telemetry_label = QLabel()
        self.rtt_label = QLabel()

        right_panel = QWidget()
        right_panel.setObjectName("sidePanel")

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(8)

        right_layout.addWidget(self.arm_label)
        right_layout.addSpacing(10)

        right_layout.addWidget(self.yaw_label)
        right_layout.addSpacing(5)

        right_layout.addWidget(self.pitch_label)
        right_layout.addWidget(self.roll_label)
        right_layout.addSpacing(10)

        right_layout.addWidget(self.throttle_label)
        right_layout.addWidget(self.steering_label)
        right_layout.addSpacing(5)

        right_layout.addWidget(self.warning_label)
        right_layout.addSpacing(5)

        right_layout.addWidget(self.motor_limit_label)
        right_layout.addWidget(self.left_motor_label)
        right_layout.addWidget(self.right_motor_label)
        right_layout.addSpacing(10)

        right_layout.addWidget(self.ultrasonic_label)
        right_layout.addStretch()

        right_layout.addWidget(self.telemetry_label)
        right_layout.addWidget(self.rtt_label)

        # --- Bottom panel ---
        bottom_panel = QWidget()
        bottom_panel.setObjectName("bottomPanel")

        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(20, 12, 20, 12)
        bottom_layout.addWidget(
            QLabel("START = ARM   |   CIRCLE / S = STOP   |   ESC / Q = STOP + QUIT")
        )

        controls = QLabel("Left stick = throttle   |   Right stick = steering")
        controls.setObjectName("muted")

        bottom_layout.addWidget(controls)

        # --- Main area ---
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.video, stretch=2.5)
        central_layout.addWidget(right_panel, stretch=1.5)

        # --- Overall layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(top_bar, stretch=0)
        layout.addWidget(central, stretch=1)
        layout.addWidget(bottom_panel, stretch=0)

        self.update()

    def update_connection_status(self) -> None:
        self.set_status(self.control_status, "IP LINK", self.state.control_connected)
        self.set_status(self.video_status, "VIDEO", self.state.video_connected)
        self.set_status(
            self.controller_status, "CONTROLLER", self.state.controller_connected
        )

    @staticmethod
    def set_status(label: QLabel, name: str, connected: bool) -> None:
        if connected:
            label.setText(f"● {name}")
            label.setStyleSheet("color: #58d68d;")
        else:
            label.setText(f"○ {name}")
            label.setStyleSheet("color: #f55b5b;")

    def update(self) -> None:
        self.update_connection_status()

        # Arm state
        if armed(self.state):
            self.arm_label.setText("ARMED - FULL PWM")
            self.arm_label.setStyleSheet(
                "color: #f4be4c; font-size: 18px; font-weight: bold;"
            )
        elif self.state.arm_requested:
            self.arm_label.setText("ARM REQUESTED")
            self.arm_label.setStyleSheet(
                "color: #f4be4c; font-size: 18px; font-weight: bold;"
            )
        else:
            self.arm_label.setText("DISARMED")
            self.arm_label.setStyleSheet(
                "color: #58d68d; font-size: 18px; font-weight: bold;"
            )

        imu_online = self.state.telemetry.get("imu_online")
        if imu_online is None or not imu_online:
            self.yaw_label.setText("IMU OFFLINE")
            self.yaw_label.setStyleSheet(ERROR_STYLE)

        else:
            yaw = self.state.telemetry.get("yaw")
            self.yaw_label.setText(
                "HEADING " + f"{yaw:05.1f}°" if yaw is not None else "---.-°"
            )
            self.yaw_label.setStyleSheet(TEXT_STYLE)

            pitch = self.state.telemetry.get("pitch")
            self.pitch_label.setText(
                "Pitch " + f"{pitch if pitch is not None else '--'}°"
            )

            roll = self.state.telemetry.get("roll")
            self.roll_label.setText("Roll " + f"{roll if roll is not None else '--'}°")

        self.throttle_label.setText(f"Throttle  {self.state.throttle:+.2f}")
        self.steering_label.setText(f"Steering  {self.state.steering:+.2f}")

        self.left_motor_label.setText(
            "L command: " + f"{self.state.telemetry.get('left_motor', 0):+d}"
        )
        self.right_motor_label.setText(
            "R command: " + f"{self.state.telemetry.get('right_motor', 0):+d}"
        )

        ultrasonic_online = self.state.telemetry.get("ultrasonic_online")
        if ultrasonic_online is None or not ultrasonic_online:
            self.ultrasonic_label.setText("Ultrasonic sensor offline")
            self.ultrasonic_label.setStyleSheet(ERROR_STYLE)
        else:
            dist = self.state.telemetry.get("ultrasonic_distance_m")
            self.ultrasonic_label.setText(
                "Free distance ahead: " + f"{dist:.2f} m"
                if dist is not None
                else "--.- m"
            )
            self.ultrasonic_label.setStyleSheet(TEXT_STYLE)

        age = telemetry_age_ms(self.state)
        age_text = "--" if age is None else f"{age:.0f} ms"
        self.telemetry_label.setText(f"Telemetry: {age_text}")

        if self.state.rtt_ms is None:
            rtt_text = "--"
        else:
            rtt_text = f"{self.state.rtt_ms:.1f} ms"
        self.rtt_label.setText(f"RTT: {rtt_text}")

        self.video.update()

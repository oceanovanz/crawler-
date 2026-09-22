from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QGroupBox
from PySide6.QtCore import Qt

from state import State
from connection_manager import ConnectionManager
from helpers import armed, telemetry_age_ms, get_mode

from .hud_widget import ImuHudWidget
from .axis_gauge_widget import AxisGauge
from .sonar_widget import SonarWidget
from .video_widget import VideoWidget

TEXT_STYLE = "color: white;"
WARNING_STYLE = "color: #f4be4c; font-weight: bold;"
ERROR_STYLE = "color: #f55b5b; font-weight: bold;"


def create_divider():
    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.HLine)
    divider.setFrameShadow(QFrame.Shadow.Sunken)
    divider.setStyleSheet("""
        background-color: #333333;
        max-height: 0.1px;
    """)
    return divider


class ControlPage(QWidget):

    def __init__(self, state: State, connection: ConnectionManager, parent=None) -> None:
        super().__init__(parent)

        self.state = state
        self.connection = connection

        # --- Video ---
        self.video = VideoWidget(state, connection)

        # --- Right panel ---
        self.imu_hud = ImuHudWidget()
        self.throttle_gauge = AxisGauge("THROTTLE")
        self.steering_gauge = AxisGauge("STEERING")
        self.arm_label = QLabel()
        self.mode_label = QLabel()
        self.left_motor_label = QLabel()
        self.right_motor_label = QLabel()

        self.sonar_radar = SonarWidget(max_distance=4.0)
        self.telemetry_label = QLabel()
        self.rtt_label = QLabel()

        imu_group = QGroupBox("ATTITUDE")
        imu_layout = QVBoxLayout(imu_group)
        imu_layout.setContentsMargins(5, 5, 5, 5)
        imu_layout.addWidget(self.imu_hud)

        control_group = QGroupBox("CONTROL")
        control_layout = QVBoxLayout(control_group)
        control_layout.setContentsMargins(10, 10, 10, 10)
        control_layout.setSpacing(10)
        row_layout = QHBoxLayout(control_group)
        row_layout.addWidget(self.arm_label, stretch=1)
        row_layout.addWidget(self.mode_label, stretch=2)
        control_layout.addLayout(row_layout)
        control_layout.addWidget(create_divider())
        control_layout.addWidget(self.throttle_gauge)
        control_layout.addWidget(self.steering_gauge)
        row_layout = QHBoxLayout(control_group)
        row_layout.addWidget(self.left_motor_label, stretch=1)
        row_layout.addWidget(self.right_motor_label, stretch=1)
        control_layout.addLayout(row_layout)

        sonar_group = QGroupBox("SONAR")
        sonar_layout = QVBoxLayout(sonar_group)
        sonar_layout.setContentsMargins(5, 5, 5, 5)
        sonar_layout.addWidget(self.sonar_radar)

        rate_group = QGroupBox()
        rate_layout = QHBoxLayout(rate_group)
        rate_layout.addWidget(self.telemetry_label, stretch=2)
        rate_layout.addWidget(self.rtt_label, stretch=1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)
        right_layout.addWidget(imu_group)
        right_layout.addWidget(control_group)
        right_layout.addWidget(sonar_group)
        right_layout.addStretch()
        right_layout.addWidget(rate_group)

        # --- Bottom panel ---
        bottom_panel = QGroupBox()
        bottom_layout = QVBoxLayout(bottom_panel)
        instructions = QLabel("START = ARM   |   CIRCLE / S = STOP   |   ESC / Q = STOP + QUIT")
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls = QLabel("Left stick = throttle   |   Right stick = steering")
        controls.setObjectName("muted")
        controls.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom_layout.addWidget(instructions)
        bottom_layout.addWidget(controls)

        # --- Main area ---
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.video, stretch=1)
        central_layout.addWidget(bottom_panel, stretch=0)

        # --- Overall layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(central, stretch=2.5)
        layout.addWidget(right_panel, stretch=1.5)

        self.update()

    def update_gui(self) -> None:
        telemetry = self.state.telemetry

        # Arm state
        if armed(self.state):
            self.arm_label.setText("ARMED")
            self.arm_label.setStyleSheet("color: #f4be4c; " "font-size: 16px; " "font-weight: bold;")
        elif self.state.arm_requested:
            self.arm_label.setText("ARM REQUESTED")
            self.arm_label.setStyleSheet("color: #f4be4c; " "font-size: 16px; " "font-weight: bold;")
        else:
            self.arm_label.setText("DISARMED")
            self.arm_label.setStyleSheet("color: #58d68d; " "font-size: 16px; " "font-weight: bold;")

        # Mode
        self.mode_label.setText("Mode: " + get_mode(self.state).upper())

        # IMU
        imu_data = telemetry.get("imu", {})
        self.imu_hud.set_data(
            yaw=imu_data.get("yaw"),
            pitch=imu_data.get("pitch"),
            roll=imu_data.get("roll"),
            online=bool(imu_data.get("online", False)),
            orientation_valid=bool(imu_data.get("orientation_valid", False)),
        )

        # Joystick
        self.throttle_gauge.set_value(self.state.throttle)
        self.steering_gauge.set_value(self.state.steering)

        # Motors
        motor_data = telemetry.get("motor", {})
        self.left_motor_label.setText("L command: " f"{motor_data.get('left_motor', 0):+d}")
        self.right_motor_label.setText("R command: " f"{motor_data.get('right_motor', 0):+d}")

        # Sonar
        sonar_data = telemetry.get("sonar", {})
        self.sonar_radar.set_measurement(
            angle=sonar_data.get("angle"),
            distance=sonar_data.get("distance"),
            online=bool(sonar_data.get("online", False)),
            timestamp=int(sonar_data.get("timestamp_ms", 0)),
        )

        # Connection status
        age = telemetry_age_ms(self.state)
        age_text = "--" if age is None else f"{age:.0f} ms"
        self.telemetry_label.setText(f"Telemetry: {age_text}")
        if self.state.rtt_ms is None:
            rtt_text = "--"
        else:
            rtt_text = f"{self.state.rtt_ms:.1f} ms"
        self.rtt_label.setText(f"RTT: {rtt_text}")

        # Video
        self.video.update()

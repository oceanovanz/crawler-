from __future__ import annotations
import asyncio

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QGroupBox,
)

from state import State
from connection_manager import ConnectionManager

from .styling import create_divider, create_combo_box
from .popups import UIEvents
from .hud_widget import ImuHudWidget
from .axis_gauge_widget import AxisGauge
from .sonar_widget import SonarWidget
from .video_widget import VideoWidget
from .map_widget import MapWidget

TEXT_STYLE = "color: white;"
WARNING_STYLE = "color: #f4be4c; font-weight: bold;"
ERROR_STYLE = "color: #f55b5b; font-weight: bold;"

SMALL_BUTTON_STYLE = """
QPushButton {
    font-size: 10px;
    padding: 2px 8px;
}
"""

ESTOP_BUTTON_STYLE = """
QPushButton {
    background-color: #c62828;
    color: white;
    font-weight: bold;
    font-size: 11px;
    border: 2px solid #7f0000;
    border-radius: 6px;
    padding: 2px 10px;
}
QPushButton:hover {
    background-color: #e53935;
}
QPushButton:pressed {
    background-color: #7f0000;
}
"""


class ControlPage(QWidget):

    def __init__(self, state: State, connection: ConnectionManager, ui_events: UIEvents, parent=None) -> None:
        super().__init__(parent)

        self.state = state
        self.connection = connection
        self.ui_events = ui_events

        # Guards against _on_mode_changed reacting to a programmatic update
        # (from update_gui syncing the dropdown to actual robot state)
        # as if it were a user-initiated change.
        self._syncing_mode_dropdown = False

        # --- Video / Map ---
        self.video = VideoWidget(state, connection)
        self.map_widget = MapWidget(state)

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.video)
        self.view_stack.addWidget(self.map_widget)
        self.view_stack.setCurrentWidget(self.video)  # video is the default view

        self.view_toggle_button = QPushButton("Show Map")
        self.view_toggle_button.setCheckable(True)
        self.view_toggle_button.clicked.connect(self._toggle_view)

        # --- Right panel ---
        self.imu_hud = ImuHudWidget()
        self.throttle_gauge = AxisGauge("THROTTLE")
        self.steering_gauge = AxisGauge("STEERING")
        self.arm_label = QLabel()
        self.left_motor_label = QLabel()
        self.right_motor_label = QLabel()

        self.arm_button = QPushButton("Arm")
        self.arm_button.setStyleSheet(SMALL_BUTTON_STYLE)
        self.arm_button.setFixedHeight(22)
        self.arm_button.clicked.connect(self._on_arm_toggle)

        self.mode_dropdown = create_combo_box(["MANUAL", "AUTO"], "MANUAL")
        self.mode_dropdown.currentTextChanged.connect(self._on_mode_changed)

        self.stop_route_button = QPushButton("Stop Route")
        self.stop_route_button.setToolTip("Pause the currently running coverage route.")
        self.stop_route_button.setStyleSheet(SMALL_BUTTON_STYLE)
        self.stop_route_button.setFixedHeight(22)
        self.stop_route_button.clicked.connect(self._on_stop_route)

        self.resume_route_button = QPushButton("Resume Route")
        self.resume_route_button.setToolTip("Resume a previously paused coverage route.")
        self.resume_route_button.setStyleSheet(SMALL_BUTTON_STYLE)
        self.resume_route_button.setFixedHeight(22)
        self.resume_route_button.clicked.connect(self._on_resume_route)

        self.estop_button = QPushButton("E-STOP")
        self.estop_button.setToolTip("Immediately disarm and cancel any running route.")
        self.estop_button.setStyleSheet(ESTOP_BUTTON_STYLE)
        self.estop_button.setFixedHeight(22)
        self.estop_button.clicked.connect(self._on_emergency_stop)

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
        control_layout.setSpacing(8)

        arm_row = QHBoxLayout()
        arm_row.addWidget(self.arm_label, stretch=2)
        arm_row.addWidget(self.arm_button, stretch=1)
        control_layout.addLayout(arm_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        mode_row.addWidget(self.mode_dropdown)
        mode_row.addStretch()
        control_layout.addLayout(mode_row)

        action_row = QHBoxLayout()
        action_row.addWidget(self.stop_route_button)
        action_row.addWidget(self.resume_route_button)
        action_row.addWidget(self.estop_button)
        control_layout.addLayout(action_row)

        control_layout.addWidget(create_divider())
        control_layout.addWidget(self.throttle_gauge)
        control_layout.addWidget(self.steering_gauge)
        motor_row = QHBoxLayout()
        motor_row.addWidget(self.left_motor_label, stretch=1)
        motor_row.addWidget(self.right_motor_label, stretch=1)
        control_layout.addLayout(motor_row)

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

        # --- View toggle row (sits above the video/map stack) ---
        view_toggle_row = QHBoxLayout()
        view_toggle_row.addStretch()
        view_toggle_row.addWidget(self.view_toggle_button)

        # --- Main area ---
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(6)
        central_layout.addLayout(view_toggle_row, stretch=0)
        central_layout.addWidget(self.view_stack, stretch=1)
        central_layout.addWidget(bottom_panel, stretch=0)

        # --- Overall layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(central, stretch=2.5)
        layout.addWidget(right_panel, stretch=1.5)

        self._sync_mode_dropdown()
        self.update()

    def _toggle_view(self) -> None:
        if self.view_stack.currentWidget() is self.video:
            self.view_stack.setCurrentWidget(self.map_widget)
            self.view_toggle_button.setText("Show Video")
        else:
            self.view_stack.setCurrentWidget(self.video)
            self.view_toggle_button.setText("Show Map")

    # ------------------------------------------------------------------
    # Button / dropdown handlers
    # ------------------------------------------------------------------

    def _on_arm_toggle(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot.\nCannot arm/disarm.")
            return

        if self.state.is_armed():
            asyncio.create_task(self.state.queue.put({"type": "stop"}))
        else:
            asyncio.create_task(self.state.queue.put({"type": "arm"}))

    def _on_mode_changed(self, text: str) -> None:
        if self._syncing_mode_dropdown:
            return  # programmatic sync from update_gui(), not a user action

        mode = text.lower()

        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot.\nCannot change mode.")
            self._sync_mode_dropdown()
            return

        # Switching to auto starts the uploaded route (see TopsideNode.set_mode),
        # so a route can't be started this way unless one's actually in place.
        if mode == "auto" and (not self.state.map_uploaded or not self.state.route_uploaded):
            self.ui_events.error.emit("Upload a map and a route before switching to Auto mode.")
            self._sync_mode_dropdown()
            return

        asyncio.create_task(self.state.queue.put({"type": "set_mode", "mode": mode}))

    def _on_stop_route(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot.\nCannot stop route.")
            return
        asyncio.create_task(self.state.queue.put({"type": "cancel_route"}))

    def _on_resume_route(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot.\nCannot resume route.")
            return
        asyncio.create_task(self.state.queue.put({"type": "resume_route"}))

    def _on_emergency_stop(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot.\nCannot send emergency stop.")
            return
        asyncio.create_task(self.state.queue.put({"type": "stop"}))

    # ------------------------------------------------------------------
    # GUI refresh
    # ------------------------------------------------------------------

    def _sync_mode_dropdown(self) -> None:
        """Reflect actual robot state in the dropdown without re-triggering a mode change."""
        self._syncing_mode_dropdown = True
        self.mode_dropdown.setCurrentText(self.state.get_mode().upper())
        self._syncing_mode_dropdown = False

    def update_gui(self) -> None:
        if not self.connection.ip_connected:
            self.state.wipe_telemetry()

        telemetry = self.state.telemetry

        # Arm state
        if self.state.is_armed():
            self.arm_label.setText("ARMED")
            self.arm_label.setStyleSheet("color: #f4be4c; " "font-size: 16px; " "font-weight: bold;")
            self.arm_button.setText("Disarm")
        elif self.state.arm_requested:
            self.arm_label.setText("ARM REQUESTED")
            self.arm_label.setStyleSheet("color: #f4be4c; " "font-size: 16px; " "font-weight: bold;")
            self.arm_button.setText("Arm")
        else:
            self.arm_label.setText("DISARMED")
            self.arm_label.setStyleSheet("color: #58d68d; " "font-size: 16px; " "font-weight: bold;")
            self.arm_button.setText("Arm")

        self._sync_mode_dropdown()

        # IMU
        imu_data = telemetry.get("imu", {})
        self.imu_hud.set_data(
            yaw=imu_data.get("yaw", None),
            pitch=imu_data.get("pitch", None),
            roll=imu_data.get("roll", None),
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
            angle=sonar_data.get("angle", None),
            distance=sonar_data.get("distance", None),
            online=bool(sonar_data.get("online", False)),
            timestamp=int(sonar_data.get("timestamp_ms", 0)),
        )

        # Connection status
        age = self.state.system.get("telemetry_age_ms", None)
        age_text = "--" if age is None else f"{age:.0f} ms"
        self.telemetry_label.setText(f"Last telemetry: {age_text}")
        if self.state.rtt_ms is None:
            rtt_text = "--"
        else:
            rtt_text = f"{self.state.rtt_ms:.1f} ms"
        self.rtt_label.setText(f"RTT: {rtt_text}")

        # Video / Map: only repaint whichever view is currently visible
        current_view = self.view_stack.currentWidget()
        if current_view is self.video:
            self.video.update()
        elif current_view is self.map_widget:
            self.map_widget.update()

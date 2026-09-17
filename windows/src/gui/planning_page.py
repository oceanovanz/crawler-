from __future__ import annotations
import asyncio
import numpy as np

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QComboBox,
    QMessageBox,
)
from state import State
from config import UserConfiguration, save_user_config
from .popups import UIEvents
from .planning_view import PlanningView


def create_spin_box(value=None, tip=None, min=0.1, max=10.0, dp=2, suffix=" m"):
    box = QDoubleSpinBox()
    box.setRange(min, max)
    box.setDecimals(dp)
    box.setSuffix(suffix)
    if value:
        box.setValue(value)
    if tip:
        box.setToolTip(tip)
    return box


def create_combo_box(items, current=None, tip=None):
    box = QComboBox()
    box.addItems(items)
    box.setStyleSheet("color: white; background-color: #1e1e1e;")
    if current:
        box.setCurrentText(current)
    if tip:
        box.setToolTip(tip)
    return box


def create_divider():
    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.HLine)
    divider.setFrameShadow(QFrame.Shadow.Sunken)
    divider.setStyleSheet("""
        background-color: #333333;
        max-height: 1px;
    """)
    return divider


class PlanningPage(QWidget):

    def __init__(self, state: State, config: UserConfiguration, ui_events: UIEvents, parent=None) -> None:
        super().__init__(parent)

        self.state = state
        self.user_config = config
        self.ui_events = ui_events
        self.view = PlanningView(config.boundary.width, config.boundary.length, config.current_pose)

        self.view.pose_selected.connect(self._pose_selected)
        self.view.pose_invalid.connect(self._pose_invalid)

        self.plan_timer = QTimer(self)
        self.plan_timer.timeout.connect(self._check_plan)
        self.plan_timer.start()

        # --- Initialise screen elements ---
        self.width_input = create_spin_box(value=config.boundary.width, min=0.0, max=10000.0)
        self.width_input.valueChanged.connect(self.update_polygon)
        self.length_input = create_spin_box(value=config.boundary.length, min=0.0, max=10000.0)
        self.length_input.valueChanged.connect(self.update_polygon)

        self.path_type = create_combo_box(
            items=["DUBIN", "REEDS_SHEPP"],
            current=config.navigation.path_type,
            tip="path type to connect routes together using curves",
        )
        self.route_type = create_combo_box(
            items=["BOUSTROPHEDON", "SNAKE", "SPIRAL"],
            current=config.navigation.route_type,
            tip="order when computing routes to order swaths",
        )

        self.headland_width = create_spin_box(
            value=config.navigation.headland_width,
            min=0.0,
            max=100.0,
            tip="border to remove from the zone from coverage planning (used for turning)",
        )
        self.headland_width.valueChanged.connect(self.update_polygon)

        self.swath_objective = create_combo_box(
            items=["LENGTH", "NUMBER", "COVERAGE"],
            current=config.navigation.swath_objective,
            tip="what metric to optimize for when evaluating different path angles",
        )
        self.swath_mode = create_combo_box(
            items=["SET_ANGLE", "BRUTE_FORCE"],
            current=config.navigation.swath_mode,
            tip="how the planner finds the angle for the swaths",
        )

        self.plan_status = QLabel("No path generated")
        self.plan_button = QPushButton("Generate Plan")
        self.plan_button.clicked.connect(self.generate_plan)

        self.select_pose_button = QPushButton("Select current pose")
        self.select_pose_button.setToolTip(
            "Click and drag on the map to select the robot's starting position and orientation."
        )
        self.select_pose_button.clicked.connect(self.begin_pose_selection)

        self.start_route_button = QPushButton("Start Route")
        self.start_route_button.setToolTip(
            "Start the generated coverage route. " "The robot will be switched to AUTO mode."
        )
        self.start_route_button.clicked.connect(self.start_route)

        # --- Layout ---
        boundary_title = QLabel("BOUNDARY")
        boundary_title.setObjectName("sectionTitle")
        boundary_form = QFormLayout()
        boundary_form.setSpacing(12)
        boundary_form.addRow("Width:", self.width_input)
        boundary_form.addRow("Length:", self.length_input)

        path_title = QLabel("PATH PLANNING")
        path_title.setObjectName("sectionTitle")
        path_form = QFormLayout()
        path_form.setSpacing(12)
        path_form.addRow("Path type:", self.path_type)
        path_form.addRow("Route type:", self.route_type)
        path_form.addRow("Border width:", self.headland_width)
        path_form.addRow("Swath objective:", self.swath_objective)
        path_form.addRow("Swath mode:", self.swath_mode)

        save_button = QPushButton("Save Configuration")
        save_button.clicked.connect(self.save_user_config)

        side_layout = QVBoxLayout()
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(15)

        side_layout.addWidget(boundary_title)
        side_layout.addLayout(boundary_form)
        side_layout.addWidget(create_divider())
        side_layout.addWidget(path_title)
        side_layout.addLayout(path_form)
        side_layout.addWidget(self.plan_status)
        side_layout.addStretch()
        side_layout.addWidget(self.plan_button)
        side_layout.addWidget(self.select_pose_button)
        side_layout.addWidget(self.start_route_button)
        side_layout.addWidget(save_button)

        side_panel = QWidget()
        side_panel.setObjectName("sidePanel")
        side_panel.setLayout(side_layout)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.view, stretch=3)
        main_layout.addWidget(side_panel, stretch=1)

        self.update_polygon()

    def update_polygon(self) -> None:
        self.view.set_boundary(
            self.width_input.value(),
            self.length_input.value(),
            self.headland_width.value(),
        )

    def begin_pose_selection(self) -> None:
        self.view.begin_pose_selection()
        self.select_pose_button.setText("Drag on map...")

    def save_user_config(self) -> None:
        self.update_user_config()
        save_user_config(self.user_config)

    def update_user_config(self) -> None:
        self.user_config.boundary.width = self.width_input.value()
        self.user_config.boundary.length = self.length_input.value()
        self.user_config.navigation.path_type = self.path_type.currentText()
        self.user_config.navigation.route_type = self.route_type.currentText()
        self.user_config.navigation.headland_width = self.headland_width.value()
        self.user_config.navigation.swath_objective = self.swath_objective.currentText()
        self.user_config.navigation.swath_mode = self.swath_mode.currentText()

    def generate_plan(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot. Cannot generate route.")
            return

        self.user_config.has_coverage_plan = False
        self.user_config.coverage_plan = None
        self.view.clear_path()

        self.plan_status.setText("Generating path...")
        self.plan_status.setStyleSheet("color: #f4be4c;")
        self.plan_button.setEnabled(False)

        self.plan_timer.start(50)

        self.update_user_config()
        plan_msg = self.user_config.navigation.plan_msg()
        asyncio.create_task(self.state.queue.put(plan_msg))

    def start_route(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot. Cannot start route.")
            return

        if not self.user_config.has_pose():
            self.ui_events.error.emit("Current pose must be selected before the route can start.")
            return

        if not self.user_config.has_coverage_plan:
            self.ui_events.error.emit("A coverage path must be generated before the route can start.")
            return

        self._show_start_route_confirmation()

    def _show_start_route_confirmation(self) -> None:
        result = QMessageBox.warning(
            self,
            "Start Route",
            (
                "Starting the route will switch the robot to AUTO mode and begin executing the coverage path.\n\n"
                "Please check that the current pose represents the current position and orientation of the crawler before continuing.\n\n"
                "Are you sure you want to continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            self._start_route_confirmed()

    def _start_route_confirmed(self) -> None:
        message = {"type": "start_route", "plan_id": self.user_config.coverage_plan["plan_id"]}
        asyncio.create_task(self.state.queue.put(message))

    def _check_plan(self) -> None:
        # not received plan yet -> skip and check again next callback
        if not self.user_config.has_coverage_plan:
            return

        # received plan -> can stop checking
        self.plan_timer.stop()

        coverage_plan = self.user_config.coverage_plan
        success = coverage_plan.get("success", False)

        if success:
            planning_time = coverage_plan.get("planning_time")
            time_sec = planning_time.get("sec", 0) + planning_time.get("nanosec", 0) * 1e-9
            self.plan_status.setText(f"Path generated ({time_sec:.2f} s)")
            self.plan_status.setStyleSheet("color: #4caf50;")
            self._display_coverage_plan(coverage_plan)
        else:
            error = coverage_plan.get("error", "unknown")
            self.plan_status.setText(f"Planning failed (error {error})")
            self.plan_status.setStyleSheet("color: #f55b5b;")
        self.plan_button.setEnabled(True)

    def _display_coverage_plan(self, coverage_plan: dict) -> None:
        if not coverage_plan:
            return

        nav_path = coverage_plan.get("nav_path")

        if not nav_path:
            return

        path = self._extract_nav_path(nav_path)
        self.view.set_path(path, 0.5)  # TODO: vacuum width

    def _extract_nav_path(self, nav_path: dict) -> list[tuple[float, float]]:
        return [(float(pose["position"]["x"]), float(pose["position"]["y"])) for pose in nav_path.get("poses", [])]

    def _pose_invalid(self) -> None:
        self.ui_events.error.emit("Starting position must be inside the boundary.")

    def _pose_selected(self, x: float, y: float, yaw: float) -> None:
        self.user_config.current_pose = np.array([x, y, yaw], dtype=float)
        msg = self.user_config.pose_msg()
        asyncio.create_task(self.state.queue.put(msg))
        self.select_pose_button.setText("Select current pose")

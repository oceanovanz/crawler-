from __future__ import annotations
import asyncio
import numpy as np

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from .styling import create_spin_box, create_combo_box, create_divider
from .popups import UIEvents
from .planning_view import PlanningView
from state import State
from config import UserConfiguration, save_user_config
from crawler_utils.path_generation import build_boundary_grid, compute_boustrophedon_path, compute_spiral_path


class PlanningPage(QWidget):

    def __init__(self, state: State, config: UserConfiguration, ui_events: UIEvents, parent=None) -> None:
        super().__init__(parent)

        self.state = state
        self.user_config = config
        self.ui_events = ui_events
        self.view = PlanningView(
            config.boundary.width, config.boundary.length, config.current_pose, config.coverage_plan
        )

        # --- Initialise screen elements ---
        self.width_input = create_spin_box(value=config.boundary.width, min=0.0, max=10000.0)
        self.width_input.valueChanged.connect(self.update_polygon)
        self.length_input = create_spin_box(value=config.boundary.length, min=0.0, max=10000.0)
        self.length_input.valueChanged.connect(self.update_polygon)

        self.route_type = create_combo_box(
            items=["BOUSTROPHEDON", "SPIRAL"], current=config.navigation.route_type, tip="type of route to generate"
        )
        self.sweep_spacing = create_spin_box(
            value=config.navigation.sweep_spacing, min=0.0, max=100.0, tip="metres between route lines"
        )
        self.safety_margin = create_spin_box(
            value=config.navigation.safety_margin, min=0.0, max=100.0, tip="safety clearance to walls/obstacles"
        )
        self.robot_radius = create_spin_box(
            value=config.navigation.robot_radius, min=0.01, max=10.0, tip="robot radius, used for wall clearance"
        )

        self.select_pose_button = QPushButton("Select intial pose")
        self.select_pose_button.setToolTip("Click and drag on the map to select the robot's position and orientation.")
        self.select_pose_button.clicked.connect(self.begin_pose_selection)

        # self.select_roi_button = QPushButton("Select ROI")
        # self.select_roi_button.setToolTip("Click and drag on the map to select the region of interest.")
        # self.select_roi_button.clicked.connect(self.begin_roi_selection)

        self.plan_status = QLabel("No path generated")
        self.plan_button = QPushButton("Generate Plan")
        self.plan_button.clicked.connect(self.generate_route)

        self.upload_map_button = QPushButton("Upload Map")
        self.upload_map_button.setToolTip("Send the boundary dimensions to the robot and publish the map.")
        self.upload_map_button.clicked.connect(self.upload_map)

        self.upload_route_button = QPushButton("Upload Route")
        self.upload_route_button.setToolTip("Send the generated coverage route to the robot.")
        self.upload_route_button.clicked.connect(self.upload_route)

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
        path_form.addRow("Route type:", self.route_type)
        path_form.addRow("Sweep spacing:", self.sweep_spacing)
        path_form.addRow("Safety margin:", self.safety_margin)
        path_form.addRow("Robot radius:", self.robot_radius)

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
        side_layout.addWidget(self.select_pose_button)
        side_layout.addWidget(self.plan_button)
        side_layout.addWidget(self.upload_map_button)
        side_layout.addWidget(self.upload_route_button)
        side_layout.addWidget(save_button)

        side_panel = QWidget()
        side_panel.setLayout(side_layout)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.view, stretch=3)
        main_layout.addWidget(side_panel, stretch=1)

        self.view.pose_selected.connect(self._pose_selected)
        self.view.pose_invalid.connect(self._pose_invalid)

        # Identity (not value) of the plan last sent via upload_route()
        self._uploaded_plan = None

    def update_polygon(self) -> None:
        self.view.set_boundary(self.width_input.value(), self.length_input.value())

    def begin_pose_selection(self) -> None:
        self.view.begin_pose_selection()
        self.select_pose_button.setText("Drag on map...")

    def save_user_config(self) -> None:
        self.update_user_config()
        save_user_config(self.user_config)

    def update_user_config(self) -> None:
        self.user_config.boundary.width = self.width_input.value()
        self.user_config.boundary.length = self.length_input.value()
        self.user_config.navigation.route_type = self.route_type.currentText()
        self.user_config.navigation.sweep_spacing = self.sweep_spacing.value()
        self.user_config.navigation.safety_margin = self.safety_margin.value()
        self.user_config.navigation.robot_radius = self.robot_radius.value()

    def generate_route(self) -> None:
        """
        Plan fully offline: build the boundary grid locally and call the
        path generator directly, no round trip to the robot involved.
        """
        self.update_user_config()
        nav = self.user_config.navigation
        boundary = self.user_config.boundary

        self.user_config.has_coverage_plan = False
        self.user_config.coverage_plan = None
        self.view.clear_path()

        self.plan_status.setText("Generating path...")
        self.plan_status.setStyleSheet("color: #f4be4c;")
        self.plan_button.setEnabled(False)

        try:
            grid = build_boundary_grid(boundary.width, boundary.length)

            if nav.route_type == "BOUSTROPHEDON":
                waypoints = compute_boustrophedon_path(grid, nav.robot_radius, nav.sweep_spacing, nav.safety_margin)
            elif nav.route_type == "SPIRAL":
                waypoints = compute_spiral_path(grid, nav.robot_radius, nav.sweep_spacing, nav.safety_margin)
            else:
                raise ValueError(f"Unknown route type: {nav.route_type}")
        except Exception as exc:
            self.plan_status.setText(f"Planning failed: {exc}")
            self.plan_status.setStyleSheet("color: #f55b5b;")
            self.plan_button.setEnabled(True)
            return

        self.plan_button.setEnabled(True)

        if not waypoints:
            self.plan_status.setText("No reachable coverage waypoints found.")
            self.plan_status.setStyleSheet("color: #f55b5b;")
            return

        self.user_config.coverage_plan = waypoints  # list[(x, y, yaw)]
        self.user_config.has_coverage_plan = True
        self.plan_status.setText(f"Path generated ({len(waypoints)} waypoints)")
        self.plan_status.setStyleSheet("color: #4caf50;")
        self.view.set_path(waypoints)

    def upload_map(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot. Cannot upload map.")
            return False

        self.update_user_config()
        asyncio.create_task(self.state.queue.put(self.user_config.map_msg()))
        return True

    def upload_route(self) -> None:
        if not self.state.control_connected:
            self.ui_events.error.emit("No IP connection to robot. Cannot upload route.")
            return False

        if not self.user_config.has_coverage_plan:
            self.ui_events.error.emit("A coverage path must be generated before it can be uploaded.")
            return False

        asyncio.create_task(self.state.queue.put(self.user_config.route_msg()))
        self._uploaded_plan = self.user_config.coverage_plan
        return True

    def has_unuploaded_plan(self) -> bool:
        return self.user_config.has_coverage_plan and self.user_config.coverage_plan is not self._uploaded_plan

    def confirm_navigate_away(self) -> bool:
        """True if navigation should proceed, False if the user chose to stay."""
        if not self.has_unuploaded_plan():
            return True

        box = QMessageBox(self)
        box.setWindowTitle("Unsaved Route")
        box.setText(
            "You have a generated route that hasn't been uploaded to the robot.\n\n"
            "What would you like to do before leaving this page?"
        )
        upload_btn = box.addButton("Upload", QMessageBox.ButtonRole.AcceptRole)
        save_btn = box.addButton("Save", QMessageBox.ButtonRole.ActionRole)
        discard_btn = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is upload_btn:
            return self.upload_map() and self.upload_route()
        elif clicked is save_btn:
            self.save_user_config()
            return True
        elif clicked is discard_btn:
            return True
        else:
            return False  # Cancel (or dialog dismissed) — stay on this page

    def _pose_invalid(self) -> None:
        self.ui_events.error.emit("Starting position must be inside the boundary.")

    def _pose_selected(self, x: float, y: float, yaw: float) -> None:
        self.user_config.current_pose = np.array([x, y, yaw], dtype=float)
        msg = self.user_config.pose_msg()
        asyncio.create_task(self.state.queue.put(msg))
        self.select_pose_button.setText("Select current pose")

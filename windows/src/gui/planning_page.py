from __future__ import annotations
import asyncio


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
)
from state import State
from config import UserConfiguration, save_user_config
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

    def __init__(self, state: State, config: UserConfiguration, parent=None) -> None:
        super().__init__(parent)

        self.state = state
        self.user_config = config
        self.view = PlanningView(config.boundary.width, config.boundary.length)

        self._had_coverage_plan = False

        self.plan_timer = QTimer(self)
        self.plan_timer.timeout.connect(self._check_plan)
        self.plan_timer.start(50)

        # --- Initialise screen elements ---
        self.width_input = create_spin_box(
            value=config.boundary.width, min=0.0, max=10000.0
        )
        self.width_input.valueChanged.connect(self.update_polygon)
        self.length_input = create_spin_box(
            value=config.boundary.length, min=0.0, max=10000.0
        )
        self.length_input.valueChanged.connect(self.update_polygon)

        self.path_type = create_combo_box(
            items=["DUBIN", "REEDS_SHEPP"],
            current=config.path_planning.path_type,
            tip="path type to connect routes together using curves",
        )
        self.route_type = create_combo_box(
            items=["BOUSTROPHEDON", "SNAKE", "SPIRAL"],
            current=config.path_planning.route_type,
            tip="order when computing routes to order swaths",
        )

        self.headland_width = create_spin_box(
            value=config.path_planning.headland_width,
            min=0.0,
            max=100.0,
            tip="border to remove from the zone from coverage planning (used for turning)",
        )
        self.headland_width.valueChanged.connect(self.update_polygon)

        self.swath_objective = create_combo_box(
            items=["LENGTH", "NUMBER", "COVERAGE"],
            current=config.path_planning.swath_objective,
            tip="what metric to optimize for when evaluating different path angles",
        )
        self.swath_mode = create_combo_box(
            items=["SET_ANGLE", "BRUTE_FORCE"],
            current=config.path_planning.swath_mode,
            tip="how the planner finds the angle for the swaths",
        )

        self.plan_status = QLabel("No path generated")
        self.plan_button = QPushButton("Generate Plan")
        self.plan_button.clicked.connect(
            lambda: asyncio.ensure_future(self.generate_plan())
        )

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
        save_button.clicked.connect(self.update_user_config)

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

    def update_user_config(self) -> None:
        self.user_config.boundary.width = self.width_input.value()
        self.user_config.boundary.length = self.length_input.value()
        self.user_config.path_planning.path_type = self.path_type.currentText()
        self.user_config.path_planning.route_type = self.route_type.currentText()
        self.user_config.path_planning.headland_width = self.headland_width.value()
        self.user_config.path_planning.swath_objective = (
            self.swath_objective.currentText()
        )
        self.user_config.path_planning.swath_mode = self.swath_mode.currentText()
        save_user_config(self.user_config)

    async def generate_plan(self) -> None:
        self.user_config.has_coverage_plan = False
        self.user_config.coverage_plan = None
        self.view.clear_path()

        self.plan_status.setText("Generating path...")
        self.plan_status.setStyleSheet("color: #f4be4c;")
        self.plan_button.setEnabled(False)

        plan_msg = {
            "type": "plan",
            "boundary": {
                "width": self.width_input.value(),
                "length": self.length_input.value(),
            },
            "path_planning": {
                "path_type": self.path_type.currentText(),
                "route_type": self.route_type.currentText(),
                "headland_width": self.headland_width.value(),
                "swath_objective": self.swath_objective.currentText(),
                "swath_mode": self.swath_mode.currentText(),
            },
        }
        await self.state.queue.put(plan_msg)

    def _check_plan(self) -> None:
        has_plan = self.user_config.has_coverage_plan

        if has_plan and not self._had_coverage_plan:

            coverage_plan = self.user_config.coverage_plan
            success = coverage_plan.get("success", False)

            if success:
                planning_time = coverage_plan.get("planning_time")
                time_sec = (
                    planning_time.get("sec", 0) + planning_time.get("nanosec", 0) * 1e-9
                )
                self.plan_status.setText(f"Path generated ({time_sec:.2f} s)")
                self.plan_status.setStyleSheet("color: #4caf50;")
                self._display_coverage_plan(coverage_plan)
            else:
                error = coverage_plan.get("error", "unknown")
                self.plan_status.setText(f"Planning failed (error {error})")
                self.plan_status.setStyleSheet("color: #f55b5b;")
            self.plan_button.setEnabled(True)

        self._had_coverage_plan = has_plan

    def _display_coverage_plan(self, coverage_plan: dict) -> None:
        if not coverage_plan:
            return

        nav_path = coverage_plan.get("nav_path")

        if not nav_path:
            return

        path = self._extract_nav_path(nav_path)
        self.view.set_path(path, 0.5)  # TODO: vacuum width

    def _extract_nav_path(self, nav_path: dict) -> list[tuple[float, float]]:
        return [
            (float(pose["position"]["x"]), float(pose["position"]["y"]))
            for pose in nav_path.get("poses", [])
        ]

from __future__ import annotations

from PySide6.QtCore import Signal
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

    back_requested = Signal()

    def __init__(self, state: State, config: UserConfiguration, parent=None) -> None:
        super().__init__(parent)

        self.state = state
        self.user_config = config
        self.view = PlanningView(config.boundary.width, config.boundary.length)

        # --- Initialise values ---
        self.width_input = create_spin_box(value=config.boundary.width, max=10000.0)
        self.width_input.valueChanged.connect(self.update_polygon)
        self.length_input = create_spin_box(value=config.boundary.length, max=10000.0)
        self.length_input.valueChanged.connect(self.update_polygon)

        self.robot_width = create_spin_box(
            value=config.rov.robot_width, tip="width or robot frame"
        )
        self.vacuum_width = create_spin_box(
            value=config.rov.vacuum_width, tip="width of vacuum head (m)"
        )
        self.min_turn_radius = create_spin_box(
            value=config.rov.min_turning_radius,
            tip="minimum turning radius for computing paths connecting route swaths (m)",
        )
        self.lin_curve_change = create_spin_box(
            value=config.rov.linear_curvature_change,
            tip="maximum linear curvature change for computing paths connecting route swaths (1/m²)",
            suffix=" 1/m²",
        )

        self.path_type = create_combo_box(
            items=["DUBIN", "REEDS_SHEPP"],
            current=config.path_planning.path_type,
            tip="default type when computing paths to connect routes together using curves",
        )
        self.route_type = create_combo_box(
            items=["BOUSTROPHEDON", "SNAKE", "SPIRAL"],
            current=config.path_planning.route_type,
            tip="default order when computing routes to order swaths",
        )

        # --- Layout ---

        boundary_title = QLabel("BOUNDARY")
        boundary_title.setObjectName("sectionTitle")
        boundary_form = QFormLayout()
        boundary_form.setSpacing(12)
        boundary_form.addRow("Width:", self.width_input)
        boundary_form.addRow("Length:", self.length_input)

        rov_title = QLabel("ROV SPECS")
        rov_title.setObjectName("sectionTitle")
        rov_form = QFormLayout()
        rov_form.setSpacing(12)
        rov_form.addRow("Robot width:", self.robot_width)
        rov_form.addRow("Vacuum width:", self.vacuum_width)
        rov_form.addRow("Minimum turning radius:", self.min_turn_radius)
        rov_form.addRow("Linear curvature change:", self.lin_curve_change)

        path_title = QLabel("PATH PLANNING")
        path_title.setObjectName("sectionTitle")
        path_form = QFormLayout()
        path_form.setSpacing(12)
        path_form.addRow("Path type:", self.path_type)
        path_form.addRow("Route type:", self.route_type)

        plan_button = QPushButton("Generate Plan")
        plan_button.clicked.connect(self.generate_plan)

        save_button = QPushButton("Save Configuration")
        save_button.clicked.connect(self.update_user_config)

        back_button = QPushButton("Back to Control")
        back_button.clicked.connect(self.back_requested.emit)

        side_layout = QVBoxLayout()
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(15)

        side_layout.addWidget(boundary_title)
        side_layout.addLayout(boundary_form)
        side_layout.addWidget(create_divider())
        side_layout.addWidget(rov_title)
        side_layout.addLayout(rov_form)
        side_layout.addWidget(create_divider())
        side_layout.addWidget(path_title)
        side_layout.addLayout(path_form)
        side_layout.addStretch()
        side_layout.addWidget(save_button)
        side_layout.addWidget(back_button)

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
        self.view.set_dimensions(self.width_input.value(), self.length_input.value())

    def update_user_config(self) -> None:
        self.user_config.boundary.width = self.width_input.value()
        self.user_config.boundary.length = self.length_input.value()
        self.user_config.rov.robot_width = self.robot_width.value()
        self.user_config.rov.vacuum_width = self.vacuum_width.value()
        self.user_config.rov.min_turn_radius = self.min_turn_radius.value()
        self.user_config.rov.lin_curve_change = self.lin_curve_change.value()
        self.user_config.path_planning.path_type = self.path_type.currentText()
        self.user_config.path_planning.route_type = self.route_type.currentText()
        save_user_config(self.user_config)

    async def generate_plan(self) -> None:
        plan_msg = {
            "type": "plan",
            "boundary": {
                "width": self.width_input.value(),
                "length": self.length_input.value(),
            },
            "rov": {
                "robot_width": self.robot_width.value(),
                "vacuum_width": self.vacuum_width.value(),
                "min_turning_radius": self.min_turn_radius.value(),
                "linear_curvature_change": self.lin_curve_change.value(),
            },
            "path_planning": {
                "path_type": self.path_type.currentText(),
                "route_type": self.route_type.currentText(),
            },
        }
        await self.state.queue.put(plan_msg)

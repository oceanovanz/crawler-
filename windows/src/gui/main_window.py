from __future__ import annotations

import asyncio
import time

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


from state import State
from connection_manager import ConnectionManager
from controller import DualSense
from helpers import armed
from config import UserConfiguration

from .popups import UIEvents, ErrorPopup
from .control_page import ControlPage
from .planning_page import PlanningPage
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):

    def __init__(
        self,
        state: State,
        user_config: UserConfiguration,
        connection: ConnectionManager,
        controller: DualSense,
        ui_events: UIEvents,
    ) -> None:
        super().__init__()

        self.state = state
        self.user_config = user_config
        self.connection = connection
        self.controller = controller

        self.setWindowTitle("Oceanova Crawler")
        self.resize(1300, 720)

        # Pages
        self.stack = QStackedWidget()
        self.control_page = ControlPage(state, connection)
        self.planning_page = PlanningPage(state, user_config, ui_events)
        self.stack.addWidget(self.control_page)
        self.stack.addWidget(self.planning_page)

        # Main layout
        self.top_bar = self.create_top_bar()
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.top_bar)
        central_layout.addWidget(self.stack)
        self.setCentralWidget(central_widget)

        # Error popup
        self.error_popup = ErrorPopup(self)
        ui_events.error.connect(self.error_popup.show_error)

        # GUI update timer
        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.update_gui)
        self.gui_timer.start(50)

        # Controller timer
        self.controller_timer = QTimer(self)
        self.controller_timer.timeout.connect(self.update_controller)
        self.controller_timer.start(20)

        self.apply_styles()

    def create_top_bar(self) -> QWidget:
        top_bar = QWidget()
        top_bar.setObjectName("topBar")

        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)

        title = QLabel("OCEANOVA CRAWLER")
        title.setObjectName("title")

        # Status indicators
        self.link_status = QLabel()
        self.video_status = QLabel()
        self.controller_status = QLabel()

        # Control Page Button
        self.control_button = QPushButton("🎮")
        self.control_button.setToolTip("Control")
        self.control_button.clicked.connect(self.show_control_page)

        # Planning Page Button
        self.plan_button = QPushButton("📋")
        self.plan_button.setToolTip("Planning")
        self.plan_button.clicked.connect(self.show_planning_page)

        # Settings Button
        self.gear_button = QPushButton("⚙")
        self.gear_button.setToolTip("Settings")
        self.gear_button.clicked.connect(self.open_settings)

        # Layout
        layout.addWidget(title)
        layout.addSpacing(20)
        layout.addWidget(self.link_status)
        layout.addWidget(self.video_status)
        layout.addWidget(self.controller_status)
        layout.addStretch()
        layout.addWidget(self.control_button)
        layout.addWidget(self.plan_button)
        layout.addWidget(self.gear_button)

        return top_bar

    def show_control_page(self) -> None:
        self.stack.setCurrentWidget(self.control_page)

    def show_planning_page(self) -> None:
        self.stack.setCurrentWidget(self.planning_page)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.user_config, self.connection, self)
        dialog.open()

    def update_controller(self) -> None:
        if not self.state.running:
            return

        asyncio.create_task(self.controller.update())

    def update_gui(self) -> None:
        if not self.state.running:
            return

        self.update_connection_status()
        self.control_page.update_gui()

    def update_connection_status(self) -> None:
        self.set_status(self.link_status, "IP LINK", self.state.control_connected)
        self.set_status(self.video_status, "VIDEO", self.state.video_connected)
        self.set_status(self.controller_status, "CONTROLLER", self.state.controller_connected)

    @staticmethod
    def set_status(label: QLabel, name: str, connected: bool) -> None:
        if connected:
            label.setText(f"● {name}")
            label.setStyleSheet("color: #58d68d;")
        else:
            label.setText(f"○ {name}")
            label.setStyleSheet("color: #f55b5b;")

    async def shutdown_from_operator(self, reason: str) -> None:
        await self.connection.stop_motors(reason)

        self.state.running = False
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()

        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            asyncio.create_task(self.shutdown_from_operator("KEYBOARD QUIT"))
            return

        if key == Qt.Key.Key_S:
            asyncio.create_task(self.connection.stop_motors("KEYBOARD STOP"))
            return

        if key == Qt.Key.Key_P:
            asyncio.create_task(self.connection.send({"type": "ping", "client_time": time.time()}))
            return

        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        if hasattr(self, "error_popup"):
            self.error_popup.position_popup()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)

        if event.type() == QEvent.Type.WindowDeactivate:
            if armed(self.state):
                asyncio.create_task(self.connection.stop_motors("WINDOW FOCUS LOST"))

    def closeEvent(self, event) -> None:
        if self.state.running:
            self.state.running = False

            asyncio.create_task(self.connection.stop_motors("WINDOW CLOSED"))

        event.accept()

    def apply_styles(self) -> None:

        self.setStyleSheet("""
            QMainWindow {
                background-color: #161e26;
            }

            QWidget {
                font-family: "Segoe UI";
                font-size: 14px;
                color: #e6edf2;
            }

            #topBar {
                background-color: #104f63;
                min-height: 45px;
                max-height: 45px;
            }

            #title {
                color: #65b9e7;
                font-size: 20px;
                font-weight: bold;
            }

            #muted {
                color: #919faa;
            }

            #sectionTitle {
                color: #65b9e7;
                font-size: 16px;
                font-weight: bold;
            }

            QGroupBox {
                color: #65b9e7;
                font-size: 16px;
                font-weight: bold;
            }

            QLabel {
                background: transparent;
            }

            QPushButton {
                background-color: #161e26;
                border: 1px solid #374652;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 20px;
            }

            QPushButton:hover {
                background-color: #24313c;
            }

            QPushButton:pressed {
                background-color: #303f4b;
            }

            QDoubleSpinBox,
            QLineEdit {
                background-color: #141414;
                border: 1px solid #919faa;
                border-radius: 4px;
                padding: 7px;
                color: #e6edf2;
            }

            QDoubleSpinBox:focus,
            QLineEdit:focus {
                border: 2px solid #65b9e7;
            }

            QDialog {
                background-color: #161e26;
            }
            """)

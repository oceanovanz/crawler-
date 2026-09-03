from __future__ import annotations

import asyncio
import time

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from state import State
from connection_manager import ConnectionManager
from controller import DualSense
from helpers import armed
from config import UserConfiguration

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
        self.main_page = ControlPage(state, connection)
        self.planning_page = PlanningPage(state, user_config)

        self.stack.addWidget(self.main_page)
        self.stack.addWidget(self.planning_page)
        self.setCentralWidget(self.stack)

        # Navigation
        self.main_page.settings_requested.connect(self.open_settings)
        self.main_page.planning_requested.connect(self.show_planning)
        self.planning_page.back_requested.connect(self.show_main)

        # GUI update timer
        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.update_gui)
        self.gui_timer.start(50)

        # Controller timer
        self.controller_timer = QTimer(self)
        self.controller_timer.timeout.connect(self.update_controller)
        self.controller_timer.start(20)

        self.apply_styles()

    def show_main(self) -> None:
        self.stack.setCurrentWidget(self.main_page)

    def show_planning(self) -> None:
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

        self.main_page.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()

        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            asyncio.create_task(self.shutdown_from_operator("KEYBOARD QUIT"))
            return

        if key == Qt.Key.Key_S:
            asyncio.create_task(self.connection.stop_motors("KEYBOARD STOP"))
            return

        if key == Qt.Key.Key_P:
            asyncio.create_task(
                self.connection.send({"type": "ping", "client_time": time.time()})
            )
            return

        super().keyPressEvent(event)

    async def shutdown_from_operator(self, reason: str) -> None:
        await self.connection.stop_motors(reason)

        self.state.running = False
        self.close()

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
                background-color: #0c1116;
            }

            QWidget {
                font-family: "Segoe UI";
                font-size: 14px;
                color: #e6edf2;
            }

            #topBar {
                background-color: #104f63;
                border-bottom: 1px solid #374652;
                min-height: 48px;
                max-height: 48px;
            }

            #title {
                color: #65b9e7;
                font-size: 18px;
                font-weight: bold;
            }

            #sidePanel {
                background-color: #161e26;
                border-left: 1px solid #374652;
            }

            #bottomPanel {
                background-color: #161e26;
                border-top: 1px solid #374652;
                min-height: 75px;
                max-height: 105px;
            }

            #muted {
                color: #919faa;
            }

            #sectionTitle {
                color: #65b9e7;
                font-size: 18px;
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

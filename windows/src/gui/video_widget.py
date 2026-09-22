from __future__ import annotations

import asyncio

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from state import State
from connection_manager import ConnectionManager


class VideoWidget(QWidget):
    """
    Displays the latest camera frame and provides snapshot/recording controls.

    The ConnectionManager remains responsible for actually taking snapshots
    and recording. This widget only requests those operations.
    """

    def __init__(self, state: State, connection: ConnectionManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.state = state
        self.connection = connection

        self.video_label = QLabel("WAITING FOR CRAWLER VIDEO")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #000000;
                color: #91a0aa;
                border: 0.5px solid #374652;
            }
            """)

        self.snapshot_button = QPushButton("📷")
        self.snapshot_button.setToolTip("Take snapshot")
        self.snapshot_button.setFixedSize(36, 30)

        self.record_button = QPushButton("🎥")
        self.record_button.setToolTip("Start/stop recording")
        self.record_button.setFixedSize(36, 30)
        self.record_indicator = QLabel("●")
        self.record_indicator.setFixedWidth(15)

        self.snapshot_button.clicked.connect(self.take_snapshot)
        self.record_button.clicked.connect(self.toggle_recording)

        toolbar = QWidget()
        toolbar.setStyleSheet("""
            QWidget {
                background-color: rgba(22, 30, 38, 210);
            }

            QPushButton {
                background-color: #e6edf2;
                color: #101010;
                border: none;
                border-radius: 4px;
                font-size: 16px;
            }

            QPushButton:hover {
                background-color: #ffffff;
            }
            """)

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 3, 5, 3)
        toolbar_layout.setSpacing(5)

        toolbar_layout.addWidget(self.snapshot_button)
        toolbar_layout.addWidget(self.record_button)
        toolbar_layout.addWidget(self.record_indicator)
        toolbar_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.video_label, stretch=1)
        layout.addWidget(toolbar, stretch=0)

        self.update_recording_indicator()

    def update(self) -> None:
        """
        Update the displayed frame from State.

        Called periodically by MainWindow.
        """
        frame = self.state.frame

        if frame is None:
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape

        image = QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format.Format_RGB888,
        ).copy()

        pixmap = QPixmap.fromImage(image)

        self.video_label.setPixmap(
            pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        self.update_recording_indicator()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update()

    def update_recording_indicator(self) -> None:
        if self.state.recording:
            self.record_indicator.setText("●")
            self.record_indicator.setStyleSheet("color: #e63232; font-size: 18px;")
        else:
            self.record_indicator.setText("●")
            self.record_indicator.setStyleSheet("color: #969696; font-size: 18px;")

    def take_snapshot(self) -> None:
        asyncio.create_task(self.connection.take_snapshot())

    def toggle_recording(self) -> None:
        asyncio.create_task(self.connection.toggle_recording())

from __future__ import annotations

import asyncio
import ipaddress
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from connection_manager import ConnectionManager
from config import UserConfiguration, save_user_config


class SettingsDialog(QDialog):
    """
    Application settings dialog.

    Settings:
        - Raspberry Pi IP address
        - Recording directory
    """

    def __init__(
        self, user_config: UserConfiguration, connection: ConnectionManager, parent=None
    ) -> None:
        super().__init__(parent)

        self.update_connection_status
        self.user_config = user_config
        self.connection = connection

        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(480)

        self.ip_edit = QLineEdit()
        self.ip_edit.setText(user_config.pi_ip)
        self.ip_edit.setPlaceholderText("192.168.88.5")

        self.record_dir_edit = QLineEdit()
        self.record_dir_edit.setText(str(user_config.record_dir))
        self.record_dir_edit.setPlaceholderText("/home/user/OceanovaCrawler/recordings")

        self.control_status = QLabel()
        self.control_status.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        form = QFormLayout()
        form.setSpacing(12)

        ip_row = QVBoxLayout()
        ip_row.addWidget(self.ip_edit)
        ip_row.addWidget(self.control_status)

        form.addRow("IP address:", ip_row)
        form.addRow("Recording directory:", self.record_dir_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

        self.update_connection_status()

    def update_connection_status(self) -> None:
        if self.connection.ip_connected:
            self.control_status.setText("● CONNECTED")
            self.control_status.setStyleSheet("color: #58d68d;")
        else:
            self.control_status.setText("○ DISCONNECTED")
            self.control_status.setStyleSheet("color: #f55b5b;")

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setStyleSheet("color: #f55b5b;")
        self.error_label.show()

    def validate_ip(self, value: str) -> bool:
        try:
            ipaddress.IPv4Address(value)
            return True, None
        except ValueError as exc:
            return False, f"Invalid IPv4 address: {exc}"

    def validate_record_dir(self, value: str) -> bool:
        if not value.strip():
            return False, "Recording directory cannot be empty"

        try:
            Path(value).expanduser()
            return True, None
        except Exception as exc:
            return False, f"Invalid recording directory: {exc}"

    def save(self) -> None:
        ip = self.ip_edit.text().strip()
        record_dir = self.record_dir_edit.text().strip()

        success, error = self.validate_ip(ip)
        if not success:
            self.show_error(error)
            return

        success, error = self.validate_record_dir(record_dir)
        if not success:
            self.show_error(error)
            return

        record_path = Path(record_dir).expanduser()

        try:
            record_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.show_error(f"Could not create recording directory: {exc}")
            return

        # Update user configuration immediately.
        self.user_config.record_dir = record_path

        # ConnectionManager handles rebuilding its URLs and reconnecting to the new IP.
        asyncio_task = self.connection.set_pi_ip(ip)

        async def finish_save() -> None:
            try:
                await asyncio_task

                if not save_user_config(self.user_config):
                    self.show_error("Failed to save configuration.")
                    return

                self.accept()

            except Exception as exc:
                self.show_error(f"Failed to apply settings: {exc}")

        asyncio.create_task(finish_save())

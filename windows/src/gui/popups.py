from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout, QWidget


class UIEvents(QObject):
    error = Signal(str)
    warning = Signal(str)
    notification = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.error_popup = None
        self.warning_popup = None
        self.notification_popup = None

    def attach_to(self, parent: QWidget) -> None:
        self.error_popup = EventPopup("error", parent)
        self.warning_popup = EventPopup("warning", parent)
        self.notification_popup = EventPopup("notification", parent)

        self.error.connect(self.error_popup.show_message)
        self.warning.connect(self.warning_popup.show_message)
        self.notification.connect(self.notification_popup.show_message)

    def emit_error(self, message: str) -> None:
        self.error.emit(message)

    def emit_warning(self, message: str) -> None:
        self.warning.emit(message)

    def emit_notification(self, message: str) -> None:
        self.notification.emit(message)

    def position_popups(self) -> None:
        if self.error_popup is not None:
            self.error_popup.position_popup()

        if self.warning_popup is not None:
            self.warning_popup.position_popup()

        if self.notification_popup is not None:
            self.notification_popup.position_popup()


class EventPopup(QFrame):
    STYLES = {
        "error": {
            "background": "#8b2020",
            "border": "#d9534f",
        },
        "warning": {
            "background": "#8a5a00",
            "border": "#f0ad4e",
        },
        "notification": {
            "background": "#206b3c",
            "border": "#4caf50",
        },
    }

    def __init__(self, event_type: str, parent=None) -> None:
        super().__init__(parent)

        if event_type not in self.STYLES:
            raise ValueError(f"Unknown event type: {event_type}")

        self.event_type = event_type
        style = self.STYLES[event_type]

        self.setObjectName("eventPopup")
        self.setMinimumWidth(300)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("eventPopupClose")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.hide)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self.message_label, 1)
        layout.addWidget(
            self.close_button,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        self.setStyleSheet(f"""
            #eventPopup {{
                background-color: {style["background"]};
                border: 1px solid {style["border"]};
                border-radius: 6px;
            }}

            #eventPopup QLabel {{
                color: white;
                font-size: 14px;
            }}

            #eventPopupClose {{
                color: white;
                background: transparent;
                border: none;
                font-size: 20px;
                font-weight: bold;
                padding: 0px;
            }}

            #eventPopupClose:hover {{
                background-color: rgba(255, 255, 255, 40);
                border-radius: 4px;
            }}
        """)

        self.hide()

    def show_message(self, message: str) -> None:
        self.message_label.setText(message)

        self.adjustSize()
        self.position_popup()

        self.raise_()
        self.show()

        self.hide_timer.start(10000)

    def position_popup(self) -> None:
        if self.parentWidget() is None:
            return

        margin = 15

        x = self.parentWidget().width() - self.width() - margin
        y = margin

        self.move(x, y)

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout


class UIEvents(QObject):
    error = Signal(str)
    warning = Signal(str)
    notification = Signal(str)


class ErrorPopup(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("errorPopup")
        self.setMinimumWidth(400)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("errorPopupClose")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.hide)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self.message_label, 1)
        layout.addWidget(
            self.close_button,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        self.setStyleSheet("""
            #errorPopup {
                background-color: #8b2020;
                border: 1px solid #d9534f;
                border-radius: 6px;
            }

            #errorPopup QLabel {
                color: white;
                font-size: 14px;
            }

            #errorPopupClose {
                color: white;
                background: transparent;
                border: none;
                font-size: 20px;
                font-weight: bold;
                padding: 0px;
            }

            #errorPopupClose:hover {
                background-color: rgba(255, 255, 255, 40);
                border-radius: 4px;
            }
        """)

        self.hide()

    def show_error(self, message: str) -> None:
        self.message_label.setText(message)

        self.adjustSize()
        self.position_popup()

        self.raise_()
        self.show()

        QTimer.singleShot(10000, self.close)

    def position_popup(self) -> None:
        if self.parentWidget() is None:
            return

        margin = 15
        x = self.parentWidget().width() - self.width() - margin
        y = margin
        self.move(x, y)

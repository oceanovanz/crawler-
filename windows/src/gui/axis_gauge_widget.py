from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget


class AxisGauge(QWidget):

    def __init__(self, label: str, parent=None):
        super().__init__(parent)

        self.label = label
        self.value = 0.0

        self.setMinimumHeight(45)

    def set_value(self, value: float) -> None:
        self.value = max(-1.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()

        painter.fillRect(self.rect(), Qt.transparent)

        # Label
        painter.setPen(QColor("#aeb7c2"))
        painter.drawText(0, 0, 80, 18, Qt.AlignLeft | Qt.AlignVCenter, self.label)

        # Value
        painter.setPen(QColor("#e6e6e6"))
        painter.drawText(w - 65, 0, 65, 18, Qt.AlignRight | Qt.AlignVCenter, f"{self.value:+.2f}")

        # Bar
        bar_y = 25
        bar_h = 8
        bar_x = 5
        bar_w = w - 10

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#343a42"))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 4, 4)

        # Centre marker
        centre_x = bar_x + bar_w / 2
        painter.setPen(QPen(QColor("#858e99"), 1))
        painter.drawLine(centre_x, bar_y - 4, centre_x, bar_y + bar_h + 4)

        # Current value
        x = centre_x + self.value * bar_w / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#58d68d"))
        if self.value >= 0:
            painter.drawRoundedRect(QRectF(centre_x, bar_y, x - centre_x, bar_h), 4, 4)
        else:
            painter.drawRoundedRect(QRectF(x, bar_y, centre_x - x, bar_h), 4, 4)

        # Position indicator
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(x, bar_y + bar_h / 2), 5, 5)

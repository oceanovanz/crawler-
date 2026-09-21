from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget


class ImuHudWidget(QWidget):
    """
    Artificial-horizon style IMU display.

    yaw, pitch, roll are in degrees.
    0 pitch = horizon through the centre.
    Positive pitch moves the horizon down.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.yaw = 0.0
        self.pitch = 0.0
        self.roll = 0.0

        self.online = False
        self.orientation_valid = False

        self.setMinimumSize(150, 150)

    def set_data(
        self, yaw: float | None, pitch: float | None, roll: float | None, online: bool, orientation_valid: bool
    ) -> None:
        self.yaw = yaw if yaw is not None else 0.0
        self.pitch = pitch if pitch is not None else 0.0
        self.roll = roll if roll is not None else 0.0

        self.online = online
        self.orientation_valid = orientation_valid

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        size = min(w, h) - 20
        radius = size / 2.0

        cx = w / 2.0
        cy = h / 2.0

        # Background
        painter.fillRect(self.rect(), QColor("#20252b"))

        # Clip everything to the attitude indicator circle
        painter.save()
        circle = self.rect().adjusted(
            int((w - size) / 2), int((h - size) / 2), -int((w - size) / 2), -int((h - size) / 2)
        )
        painter.setClipRegion(circle)

        # Horizon
        pitch_pixels = self.pitch * 3.0  # Pitch scale
        painter.translate(cx, cy)
        painter.rotate(-self.roll)  # rotate the entire horizon
        horizon_y = pitch_pixels  # positive pitch means horizon moves down
        large = radius * 3.0

        # Sky
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#45a9d8"))
        painter.drawRect(-large, -large, large * 2, horizon_y + large)

        # Ground
        painter.setBrush(QColor("#4aa85c"))
        painter.drawRect(-large, horizon_y, large * 2, large * 2)

        # Pitch reference lines
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1))

        for pitch_angle in (-20, -10, 10, 20):
            y = pitch_pixels - pitch_angle * 3.0
            line_width = 25 if abs(pitch_angle) == 10 else 18
            painter.drawLine(QPointF(-line_width, y), QPointF(line_width, y))

        painter.restore()

        # Outer circle
        painter.setPen(QPen(QColor("#c7d0d9"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(size), int(size))

        # Aircraft reference symbol
        painter.setPen(QPen(QColor("#f0d44a"), 2))

        painter.drawLine(QPointF(cx - 32, cy), QPointF(cx - 8, cy))
        painter.drawLine(QPointF(cx + 8, cy), QPointF(cx + 32, cy))
        painter.drawLine(QPointF(cx - 8, cy), QPointF(cx, cy + 5))
        painter.drawLine(QPointF(cx + 8, cy), QPointF(cx, cy + 5))

        # Roll indicator at top
        painter.setPen(QPen(QColor("#eeeeee"), 1))

        for roll_angle in (-30, -20, -10, 10, 20, 30):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-roll_angle)
            painter.drawLine(QPointF(0, -radius + 3), QPointF(0, -radius + 10))
            painter.restore()

        # Data text
        painter.setFont(QFont("Sans", 9))
        if not self.online:
            painter.setPen(QColor("#ff5c5c"))
            text = "IMU OFFLINE"
            painter.drawText(0, 0, w, h, Qt.AlignCenter, text)
            return

        if not self.orientation_valid:
            painter.setPen(QColor("#f4be4c"))
            text = "ORIENTATION INVALID"
            painter.drawText(0, 0, w, h, Qt.AlignCenter, text)

        # Bottom-left attitude readout
        painter.setPen(QColor("#e6e6e6"))
        painter.setFont(QFont(painter.font().family(), 12))
        painter.drawText(8, 0 + 30, f"R: {self.roll:.1f}°")
        painter.drawText(8, cy, f"P: {self.pitch:.1f}°")
        painter.drawText(8, h - 30, f"Y: {self.yaw:.1f}°")

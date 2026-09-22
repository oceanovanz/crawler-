from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPolygonF, QPainterPath
from PySide6.QtCore import Qt, QPointF
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

        self.setMinimumSize(420, 130)

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

        h = self.height()

        # Background
        painter.fillRect(self.rect(), QColor("#20252b"))

        # Layout
        hud_cx = 65
        hud_cy = h / 2
        hud_radius = min(58, h / 2 - 10)

        # --- Artificial horizon ---
        painter.save()

        path = QPainterPath()
        path.addEllipse(QPointF(hud_cx, hud_cy), hud_radius, hud_radius)
        painter.setClipPath(path)

        painter.translate(hud_cx, hud_cy)
        painter.rotate(-self.roll)  # Roll rotates the horizon
        pitch_pixels = self.pitch * 2.5  # Pitch moves the horizon
        horizon_y = pitch_pixels
        large = hud_radius * 3

        # Sky
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#45a9d8"))
        painter.drawRect(-large, -large, large * 2, horizon_y + large)

        # Ground
        painter.setBrush(QColor("#4aa85c"))
        painter.drawRect(-large, horizon_y, large * 2, large * 2)

        # Horizon line
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        painter.drawLine(QPointF(-large, horizon_y), QPointF(large, horizon_y))

        # --- Pitch ladder ---
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))

        for pitch_angle in range(-20, 21, 5):
            if pitch_angle == 0:
                continue

            y = horizon_y - pitch_angle * 2.5

            # Make 10° markings longer.
            if abs(pitch_angle) % 10 == 0:
                line_width = 18
            else:
                line_width = 10

            painter.drawLine(QPointF(-line_width, y), QPointF(line_width, y))

        painter.restore()

        # --- Outer attitude circle ---
        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(
                QColor("#e0e5ea"),
                1.5,
            )
        )
        painter.drawEllipse(QPointF(hud_cx, hud_cy), hud_radius, hud_radius)

        # --- Roll markings ---
        painter.setPen(QPen(QColor("#e0e5ea"), 1))

        for roll_angle in (-30, -20, -10, 10, 20, 30):
            painter.save()

            painter.translate(hud_cx, hud_cy)
            painter.rotate(-roll_angle)
            painter.drawLine(QPointF(0, -hud_radius + 2), QPointF(0, -hud_radius + 8))
            painter.restore()

        # --- Roll pointer ---
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        triangle = QPolygonF(
            [
                QPointF(hud_cx, hud_cy - hud_radius + 2),
                QPointF(hud_cx - 4, hud_cy - hud_radius + 8),
                QPointF(hud_cx + 4, hud_cy - hud_radius + 8),
            ]
        )
        painter.drawPolygon(triangle)

        # --- Aircraft reference symbol ---
        painter.setPen(QPen(QColor("#f0d44a"), 2))

        # Left wing
        painter.drawLine(QPointF(hud_cx - 27, hud_cy), QPointF(hud_cx - 7, hud_cy))

        # Right wing
        painter.drawLine(QPointF(hud_cx + 7, hud_cy), QPointF(hud_cx + 27, hud_cy))

        # Centre
        painter.drawLine(QPointF(hud_cx - 7, hud_cy), QPointF(hud_cx, hud_cy + 4))
        painter.drawLine(QPointF(hud_cx + 7, hud_cy), QPointF(hud_cx, hud_cy + 4))

        # --- R / P / Y values ---
        text_x = hud_cx + hud_radius + 25
        label_font = QFont("Sans", 11)
        value_font = QFont("Sans", 11)

        # Roll
        painter.setFont(label_font)
        painter.setPen(QColor("#e6e6e6"))
        painter.drawText(int(text_x), int(hud_cy - 30), "R:")
        painter.setFont(value_font)
        painter.setPen(QColor("#f4c542"))
        painter.drawText(int(text_x + 24), int(hud_cy - 30), f"{self.roll:.1f}°")

        # Pitch
        painter.setFont(label_font)
        painter.setPen(QColor("#e6e6e6"))
        painter.drawText(int(text_x), int(hud_cy + 5), "P:")
        painter.setFont(value_font)
        painter.setPen(QColor("#f4c542"))
        painter.drawText(int(text_x + 24), int(hud_cy + 5), f"{self.pitch:.1f}°")

        # Yaw
        painter.setFont(label_font)
        painter.setPen(QColor("#e6e6e6"))
        painter.drawText(int(text_x), int(hud_cy + 40), "Y:")
        painter.setFont(value_font)
        painter.setPen(QColor("#f4c542"))
        painter.drawText(int(text_x + 24), int(hud_cy + 40), f"{self.yaw:.1f}°")

        # Status separator
        separator_x = int(text_x + 95)
        painter.setPen(QPen(QColor("#39434d"), 1))
        painter.drawLine(QPointF(separator_x, 10), QPointF(separator_x, h - 10))

        # Status indicators
        status_x = separator_x + 20

        # IMU Online
        status_y = hud_cy - 22
        if self.online:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#58d68d"))
            painter.drawEllipse(QPointF(status_x, status_y), 5, 5)
            painter.setPen(QColor("#c7d0d9"))
            painter.setFont(QFont("Sans", 9))
            painter.drawText(int(status_x + 14), int(status_y + 4), "IMU Online")

        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ff5c5c"))
            painter.drawEllipse(QPointF(status_x, status_y), 5, 5)
            painter.setPen(QColor("#c7d0d9"))
            painter.setFont(QFont("Sans", 9))
            painter.drawText(int(status_x + 14), int(status_y + 4), "IMU Offline")

        # Orientation valid
        status_y += 34
        painter.setPen(QPen(QColor("#58d68d" if self.orientation_valid else "#f4be4c"), 2))
        if self.orientation_valid:
            # Check mark
            painter.drawLine(
                QPointF(status_x - 5, status_y),
                QPointF(status_x - 1, status_y + 4),
            )
            painter.drawLine(
                QPointF(status_x - 1, status_y + 4),
                QPointF(status_x + 6, status_y - 5),
            )
        else:
            # Warning/exclamation marker
            painter.drawLine(QPointF(status_x, status_y - 5), QPointF(status_x, status_y + 3))
            painter.drawPoint(QPointF(status_x, status_y + 7))

        painter.setPen(QColor("#c7d0d9"))
        painter.setFont(QFont("Sans", 9))

        painter.drawText(
            int(status_x + 14),
            int(status_y + 4),
            "Orientation Valid" if self.orientation_valid else "Orientation Invalid",
        )

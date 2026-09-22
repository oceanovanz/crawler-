from collections import deque
import math

from PySide6.QtCore import QTimer, Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget


class SonarWidget(QWidget):

    def __init__(self, max_distance=5.0, parent=None):
        super().__init__(parent)

        self.max_distance = max_distance

        # state
        self.online = False

        # sonar history
        self.measurements = deque(maxlen=360)

        # Revolution tracking
        self.rev_start_time = None
        self.prev_timestamp = None
        self.revolution_periods = deque(maxlen=5)
        self.spr = 0.0

        # fade configuration
        self.fade_duration_ms = 5000
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self.update)
        self.fade_timer.start(33)  # ~30 FPS

        self.setMinimumSize(240, 240)

    def set_measurement(self, angle: float | None, distance: float | None, online: bool, timestamp: int) -> None:
        self.online = online

        if angle is None:
            return

        # Calculate revolutions per second
        if int(angle) == 90 and timestamp > 0:
            if self.rev_start_time is not None:
                dt = (timestamp - self.rev_start_time) / 1000
                self.revolution_periods.append(dt)
                self.spr = sum(self.revolution_periods) / len(self.revolution_periods)
            self.rev_start_time = timestamp

        # Store measurement
        self.measurements.append((angle, distance, timestamp))

        self.prev_timestamp = timestamp
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        painter.fillRect(self.rect(), QColor("#20252b"))

        cx = w / 2
        cy = h / 2
        radius = min(w, h) / 2 - 30

        # Offline
        if not self.online:
            painter.setPen(QColor("#ff5c5c"))
            painter.drawText(self.rect(), Qt.AlignCenter, "SONAR OFFLINE")
            return

        # Radar rings
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#58d68d"), 1, Qt.SolidLine))
        for i in range(1, 5):
            r = radius * i / 4
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # Crosshair
        painter.drawLine(QPointF(cx - radius, cy), QPointF(cx + radius, cy))
        painter.drawLine(QPointF(cx, cy - radius), QPointF(cx, cy + radius))

        # Cardinal directions
        painter.setPen(QColor("#aeb7c2"))
        painter.drawText(int(cx - 5), int(cy - radius - 8), "0°")
        painter.drawText(int(cx + radius + 5), int(cy + 7), "90°")
        painter.drawText(int(cx - 17), int(cy + radius + 14), "180°")
        painter.drawText(int(cx - radius - 35), int(cy + 7), "270°")

        # Historical sonar measurements
        now_timestamp = self.prev_timestamp
        painter.setPen(QPen(QColor("#ff3b30"), 3))
        for angle, distance, timestamp in self.measurements:
            age = now_timestamp - timestamp
            fade = max(0.0, 1.0 - age / self.fade_duration_ms)  # 0 == fully visible, fade_duration == invisible
            if fade <= 0:
                continue

            alpha = int(255 * fade)
            theta = math.radians(angle)

            # draw scan line
            x = cx + radius * math.sin(theta)
            y = cy - radius * math.cos(theta)
            painter.setPen(QPen(QColor(88, 214, 141, alpha / 2), 2))
            painter.drawLine(QPointF(cx, cy), QPointF(x, y))

            if distance is None or distance <= 0 or distance > self.max_distance:
                continue

            # draw object
            r = (distance / self.max_distance) * radius
            x = cx + r * math.sin(theta)
            y = cy - r * math.cos(theta)
            painter.setPen(QPen(QColor(255, 60, 40, alpha), 2))
            painter.drawPoint(QPointF(x, y))

        # Centre
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#58d68d"))
        painter.drawEllipse(QPointF(cx, cy), 4, 4)

        # Distance
        painter.setPen(QColor("#aeb7c2"))
        painter.setFont(QFont(painter.font().family(), 5))
        for i in range(1, 5):
            r = radius * i / 4
            d = self.max_distance * i / 4
            painter.drawText(int(cx + 2), int(cy - r - 2), f"{d:.1f} m")

        # Revolution period
        painter.setPen(QColor("#58d68d"))
        painter.setFont(QFont(painter.font().family(), 8))
        painter.drawText(8, 18, f"{self.spr:.2f} s/rev")

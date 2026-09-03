from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget

from config import UserConfiguration


class PlanningView(QWidget):
    """
    Displays the current planning boundary.

    Coordinates are in metres internally and transformed to
    screen coordinates for rendering.
    """

    def __init__(self, width_m: float, length_m: float, parent=None) -> None:
        super().__init__(parent)

        self.width_m = width_m
        self.length_m = length_m

        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: white;")

    def set_dimensions(self, width_m: float, length_m: float) -> None:
        self.width_m = width_m
        self.length_m = length_m
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, Qt.GlobalColor.white)

        self.draw_grid(painter)
        # self.draw_axes(painter)
        self.draw_polygon(painter)

    def draw_grid(self, painter: QPainter) -> None:
        width = self.width()
        height = self.height()

        spacing = 40

        pen = QPen(Qt.GlobalColor.lightGray, 1)
        painter.setPen(pen)

        x = 0
        while x <= width:
            painter.drawLine(x, 0, x, height)
            x += spacing

        y = 0
        while y <= height:
            painter.drawLine(0, y, width, y)
            y += spacing

    def draw_axes(self, painter: QPainter) -> None:
        cx = self.width() / 2
        cy = self.height() / 2

        pen = QPen(Qt.GlobalColor.darkGray, 1)
        painter.setPen(pen)

        painter.drawLine(0, int(cy), self.width(), int(cy))
        painter.drawLine(int(cx), 0, int(cx), self.height())

        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(self.width() - 35, int(cy) - 5, "+X")
        painter.drawText(int(cx) + 5, 18, "+Y")
        painter.drawText(int(cx) + 5, int(cy) - 5, "0")

    def draw_polygon(self, painter: QPainter) -> None:
        if self.width_m <= 0 or self.length_m <= 0:
            return

        padding = 60

        available_width = self.width() - 2 * padding
        available_height = self.height() - 2 * padding

        if available_width <= 0 or available_height <= 0:
            return

        scale = min(available_width / self.length_m, available_height / self.width_m)

        polygon_width = self.width_m * scale
        polygon_length = self.length_m * scale

        cx = self.width() / 2
        cy = self.height() / 2

        left = cx - polygon_length / 2
        right = cx + polygon_length / 2
        top = cy - polygon_width / 2
        bottom = cy + polygon_width / 2

        pen = QPen(Qt.GlobalColor.black, 3)

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.drawRect(int(left), int(top), int(polygon_length), int(polygon_width))

        # Dimension labels
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(int(cx - 25), int(top - 10), f"{self.length_m:g} m")
        painter.drawText(int(right + 10), int(cy), f"{self.width_m:g} m")

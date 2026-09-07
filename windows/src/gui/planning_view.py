from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QFont, QColor
from PySide6.QtWidgets import QWidget


class PlanningView(QWidget):
    """
    Displays the current planning boundary.

    Coordinates are in metres internally and transformed to
    screen coordinates for rendering.
    """

    def __init__(self, width_m: float, length_m: float, parent=None) -> None:
        super().__init__(parent)

        self.boundary_width = width_m
        self.boundary_length = length_m
        self.path: Optional[list[tuple[float, float]]] = None
        self.path_width: float = 0.5  # TODO: get vacuum width
        self.border_width = None

        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: white;")

    def set_boundary(self, width_m: float, length_m: float, border: float) -> None:
        self.boundary_width = width_m
        self.boundary_length = length_m
        self.border_width = border
        self.clear_path()
        self.update()

    def set_path(self, path: list[tuple[float, float]], width: float) -> None:
        self.path = path
        self.path_width = width
        self.update()

    def clear_path(self) -> None:
        self.path = None
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, Qt.GlobalColor.white)

        self._draw_grid(painter)
        self._draw_boundary(painter)
        self._draw_path(painter)

    def _draw_grid(self, painter: QPainter) -> None:
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

    def _draw_boundary(self, painter: QPainter) -> None:
        if self.boundary_width <= 0 or self.boundary_length <= 0:
            return

        padding = 100
        available_width = self.width() - 2 * padding
        available_height = self.height() - 2 * padding

        if available_width <= 0 or available_height <= 0:
            return

        self.scale = min(
            available_width / self.boundary_length,
            available_height / self.boundary_width,
        )

        polygon_width = self.boundary_width * self.scale
        polygon_length = self.boundary_length * self.scale

        cx = self.width() / 2
        cy = self.height() / 2

        left = cx - polygon_length / 2
        right = cx + polygon_length / 2
        top = cy - polygon_width / 2

        pen = QPen(Qt.GlobalColor.black, 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(int(left), int(top), int(polygon_length), int(polygon_width))

        # Dimension labels
        painter.setFont(QFont("Segoe UI", 12))
        painter.drawText(int(cx - 25), int(top - 20), f"{self.boundary_length:g} m")
        painter.drawText(int(right + 20), int(cy + 15), f"{self.boundary_width:g} m")

        if self.border_width is not None and self.border_width > 0:
            inner_length = polygon_length - (2 * self.border_width) * self.scale
            inner_width = polygon_width - (2 * self.border_width) * self.scale
            left = cx - inner_length / 2
            top = cy - inner_width / 2
            pen = QPen(QColor(255, 0, 0), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(int(left), int(top), int(inner_length), int(inner_width))

    def _draw_path(self, painter: QPainter) -> None:
        if not self.path or len(self.path) < 2:
            return

        # Coverage width.
        coverage_colour = QColor(74, 100, 226, 70)
        coverage_pen = QPen(
            coverage_colour,
            max(1, int(self.path_width * self.scale)),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.FlatCap,
            Qt.PenJoinStyle.RoundJoin,
        )

        painter.setPen(coverage_pen)

        points = [self._world_to_screen(x, y) for x, y in self.path]

        for p1, p2 in zip(points[:-1], points[1:]):
            painter.drawLine(p1, p2)

        # Actual path.
        path_colour = QColor(30, 60, 140, 255)
        path_pen = QPen(
            path_colour,
            2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )

        painter.setPen(path_pen)

        for p1, p2 in zip(points[:-1], points[1:]):
            painter.drawLine(p1, p2)

    def _world_to_screen(self, x: float, y: float) -> QPointF:
        cx = self.width() / 2.0
        cy = self.height() / 2.0

        sx = cx + x * self.scale
        sy = cy - y * self.scale

        return QPointF(sx, sy)

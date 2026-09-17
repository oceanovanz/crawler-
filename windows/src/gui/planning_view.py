from __future__ import annotations
import math
from typing import Optional

from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QFont, QColor
from PySide6.QtWidgets import QWidget


class PlanningView(QWidget):
    """
    Displays the current planning boundary and path.

    Coordinates are in metres internally and transformed to
    screen coordinates for rendering.

    Coordinate System:

                  +Y
                  ↑
                  │
          (-x,+y) │ (+x,+y)
                  │
        ──────────┼──────────→ +X
                  │
          (-x,-y) │ (+x,-y)
                  │

    """

    pose_selected = Signal(float, float, float)
    pose_invalid = Signal()

    def __init__(self, width_m: float, length_m: float, pose: tuple, parent=None) -> None:
        super().__init__(parent)

        self.boundary_width = width_m
        self.boundary_length = length_m
        self.path: Optional[list[tuple[float, float]]] = None
        self.path_width: float = 0.5  # TODO: get vacuum width
        self.border_width = None

        self.selecting_pose = False
        self.pose_start: QPointF | None = None
        self.pose_current: QPointF | None = None
        self.pose = pose

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

    def begin_pose_selection(self) -> None:
        self.selecting_pose = True
        self.pose_start = None
        self.pose_current = None

        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

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

    def _draw_pose(self, painter: QPainter) -> None:
        if self.selecting_pose:
            if self.pose_start is None or self.pose_current is None:
                return

            start = self.pose_start
            end = self.pose_current

        else:
            if self.pose is None:
                return

            x, y, yaw = self.pose
            start = self._world_to_screen(x, y)
            arrow_length = 1.0 * self.scale
            end = QPointF(
                start.x() + math.cos(yaw) * arrow_length,
                start.y() - math.sin(yaw) * arrow_length,
            )

        pen = QPen(
            QColor(21, 148, 25),
            3.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )

        painter.setPen(pen)
        painter.drawLine(start, end)

        # Arrow head
        angle = math.atan2(-(end.y() - start.y()), end.x() - start.x())

        head_length = 12.0
        head_angle = math.radians(25.0)

        p1 = QPointF(
            end.x() - head_length * math.cos(angle - head_angle),
            end.y() + head_length * math.sin(angle - head_angle),
        )

        p2 = QPointF(
            end.x() - head_length * math.cos(angle + head_angle),
            end.y() + head_length * math.sin(angle + head_angle),
        )

        painter.drawLine(end, p1)
        painter.drawLine(end, p2)

        # Start point
        painter.setBrush(QColor(30, 30, 30))
        painter.drawEllipse(start, 5.0, 5.0)

    def _world_to_screen(self, x: float, y: float) -> QPointF:
        cx = self.width() / 2.0
        cy = self.height() / 2.0

        sx = cx + x * self.scale
        sy = cy - y * self.scale

        return QPointF(sx, sy)

    def _screen_to_world(self, point: QPointF) -> tuple[float, float]:
        cx = self.width() / 2.0
        cy = self.height() / 2.0

        x = (point.x() - cx) / self.scale
        y = (cy - point.y()) / self.scale

        return x, y

    def _point_inside_boundary(self, x: float, y: float) -> bool:
        half_width = self.boundary_width / 2.0
        half_length = self.boundary_length / 2.0

        return -half_length <= x <= half_length and -half_width <= y <= half_width

    def _finish_pose_selection(self) -> None:
        start = self.pose_start
        end = self.pose_current

        if start is None or end is None:
            return

        dx = end.x() - start.x()
        dy = end.y() - start.y()

        # Avoid accepting an essentially zero-length drag
        if math.hypot(dx, dy) < 5.0:
            return

        world_x, world_y = self._screen_to_world(start)

        # Validate point
        if not self._point_inside_boundary(world_x, world_y):
            self.pose_start = None
            self.pose_current = None
            self.pose_invalid.emit()
            return

        world_dx = dx
        world_dy = -dy  # world coords y=up, Qt coords y=down

        yaw = math.atan2(world_dy, world_dx)

        self.pose = (world_x, world_y, yaw)
        self.selecting_pose = False
        self.pose_start = None
        self.pose_current = None

        self.unsetCursor()
        self.update()

        self.pose_selected.emit(world_x, world_y, yaw)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, Qt.GlobalColor.white)

        self._draw_grid(painter)
        self._draw_boundary(painter)
        self._draw_path(painter)
        self._draw_pose(painter)

    def mousePressEvent(self, event) -> None:
        if self.selecting_pose and event.button() == Qt.MouseButton.LeftButton:
            self.pose_start = event.position()
            self.pose_current = event.position()
            self.update()

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.selecting_pose and self.pose_start is not None:
            self.pose_current = event.position()
            self.update()

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.selecting_pose and event.button() == Qt.MouseButton.LeftButton and self.pose_start is not None:
            self.pose_current = event.position()

            self._finish_pose_selection()

            event.accept()
            return

        super().mouseReleaseEvent(event)

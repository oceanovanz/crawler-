import math
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

UNKNOWN_COLOR = QColor(120, 120, 120)
ROBOT_COLOR = QColor(220, 30, 30)
ROBOT_RADIUS_PX = 6
ROBOT_HEADING_LENGTH_PX = 16


class MapWidget(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        self._map_pixmap: Optional[QPixmap] = None
        # Cached alongside the pixmap so paintEvent can convert world -> pixel
        # coordinates without touching state.map (which may change concurrently).
        self._map_width = 0
        self._map_height = 0
        self._resolution = 1.0
        self._origin_x = 0.0
        self._origin_y = 0.0

        self.setMinimumSize(300, 300)

        if self.state.map:
            self.update_map()

    def update_map(self) -> None:
        """Rebuild the cached map pixmap from self.state.map. Call this once
        per incoming map message, not from paintEvent."""
        grid = self.state.map
        if grid is None:
            self._map_pixmap = None
            self.update()
            return

        width = grid["width"]
        height = grid["height"]

        self._map_width = width
        self._map_height = height
        self._resolution = grid["resolution"]
        self._origin_x = grid["origin"]["x"]
        self._origin_y = grid["origin"]["y"]

        # Vectorized occupancy -> grayscale, rather than a Python per-pixel
        # loop, since maps can be hundreds of thousands of cells.
        cells = np.asarray(grid["data"], dtype=np.int16).reshape(height, width)

        gray = np.empty((height, width), dtype=np.uint8)
        known = cells >= 0
        # 0 (free) -> 255 white, 100 (occupied) -> 0 black
        gray[known] = np.clip(255 - (cells[known] * 255 // 100), 0, 255).astype(np.uint8)
        gray[~known] = 0  # placeholder; painted over with UNKNOWN_COLOR below

        rgb = np.dstack([gray, gray, gray])
        rgb[~known] = (UNKNOWN_COLOR.red(), UNKNOWN_COLOR.green(), UNKNOWN_COLOR.blue())

        # OccupancyGrid row 0 is the smallest y; Qt images have row 0 at the
        # top, so flip vertically for a visually correct (north-up) image.
        rgb = np.flipud(rgb)
        rgb = np.ascontiguousarray(rgb)

        image = QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888)
        # QImage doesn't copy the buffer by default; rgb must outlive it, so
        # copy() detaches it into Qt-owned memory before rgb goes out of scope.
        self._map_pixmap = QPixmap.fromImage(image.copy())

        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        if self.state.has_new_map:
            self.update_map()
            self.state.has_new_map = False

        if self._map_pixmap is None:
            painter.fillRect(rect, Qt.GlobalColor.darkGray)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for map...")
            return

        draw_rect = self._fit_rect(rect, self._map_pixmap.width(), self._map_pixmap.height())
        painter.drawPixmap(draw_rect, self._map_pixmap, QRectF(self._map_pixmap.rect()))

        self._draw_robot(painter, draw_rect)

    def _fit_rect(self, outer: QRectF, content_w: int, content_h: int) -> QRectF:
        """Largest rect that fits `outer`, preserving the map's aspect ratio, centered."""
        scale = min(outer.width() / content_w, outer.height() / content_h)
        w, h = content_w * scale, content_h * scale
        x = outer.x() + (outer.width() - w) / 2.0
        y = outer.y() + (outer.height() - h) / 2.0
        return QRectF(x, y, w, h)

    def _draw_robot(self, painter: QPainter, draw_rect: QRectF) -> None:
        pose = self.state.pose
        if not pose or self._map_pixmap is None:
            return

        px, py = self._world_to_pixel(pose["position"]["x"], pose["position"]["y"])

        scale_x = draw_rect.width() / self._map_width
        scale_y = draw_rect.height() / self._map_height
        screen_x = draw_rect.x() + px * scale_x
        screen_y = draw_rect.y() + py * scale_y

        painter.setBrush(ROBOT_COLOR)
        painter.setPen(ROBOT_COLOR)
        painter.drawEllipse(QPointF(screen_x, screen_y), ROBOT_RADIUS_PX, ROBOT_RADIUS_PX)

        # Image y grows downward while yaw is measured counter-clockwise in
        # the map frame (y grows "up"), so negate yaw for the on-screen heading.
        yaw = pose["yaw"]
        heading_x = screen_x + ROBOT_HEADING_LENGTH_PX * math.cos(-yaw)
        heading_y = screen_y + ROBOT_HEADING_LENGTH_PX * math.sin(-yaw)
        painter.drawLine(QPointF(screen_x, screen_y), QPointF(heading_x, heading_y))

    def _world_to_pixel(self, world_x: float, world_y: float) -> tuple[float, float]:
        """World (map frame, meters) -> pixel coords in the cached (pre-flip) map image."""
        col = (world_x - self._origin_x) / self._resolution
        row = (world_y - self._origin_y) / self._resolution
        # The pixmap was flipped vertically in update_map(), so row 0 (bottom
        # of the world) is now at the bottom of the image, not the top.
        pixel_y = self._map_height - row
        return col, pixel_y

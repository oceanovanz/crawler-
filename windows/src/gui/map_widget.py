import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

UNKNOWN_COLOR = QColor(120, 120, 120)
ROBOT_COLOR = QColor(30, 30, 220)
ROBOT_RADIUS_PX = 10
ROBOT_HEADING_LENGTH_PX = 16

BACKGROUND_COLOR = QColor(50, 50, 50)
GRID_COLOR = QColor(100, 100, 100)
GRID_LABEL_COLOR = QColor(170, 170, 170)
GRID_MARGIN_M = 1.0  # how far the grid extends past the map boundary
GRID_TARGET_PX = 60.0  # aim for roughly this many pixels between grid lines

TRACE_COLOR = QColor(40, 200, 80, 140)  # wide, semi-transparent green
TRACE_WIDTH_PX = 6.0
TRACE_MIN_STEP_M = 0.05  # don't record a new trace point closer than this to the last one
MAX_TRACE_POINTS = 5000

ROUTE_LINE_COLOR = QColor(220, 40, 40)
ROUTE_LINE_WIDTH_PX = 1.5
ROUTE_POINT_COLOR = QColor(220, 40, 40)
ROUTE_POINT_RADIUS_PX = 3.0


def _nice_grid_spacing(scale_px_per_m: float, target_px: float = GRID_TARGET_PX) -> float:
    """Pick a 'nice' (1/2/5 x 10^n) grid spacing in metres so lines land roughly target_px apart."""
    if scale_px_per_m <= 0:
        return 1.0
    raw = target_px / scale_px_per_m
    magnitude = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 5, 10):
        candidate = magnitude * mult
        if candidate >= raw:
            return candidate
    return magnitude * 10


@dataclass
class _ViewTransform:
    """World (map frame, metres) -> screen (widget pixels), covering a padded view box."""

    scale: float  # pixels per metre
    vx_min: float
    vx_max: float
    vy_min: float
    vy_max: float
    offset_x: float
    offset_y: float

    def to_screen(self, wx: float, wy: float) -> QPointF:
        sx = self.offset_x + (wx - self.vx_min) * self.scale
        sy = self.offset_y + (self.vy_max - wy) * self.scale  # world +y is "up"; screen +y is down
        return QPointF(sx, sy)


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

        # Robot trace: recorded locally, capped, and only grown when the
        # robot has actually moved since the last recorded point.
        self._trace: deque[tuple[float, float]] = deque(maxlen=MAX_TRACE_POINTS)

        self.setMinimumSize(300, 300)

        # --- Overlay controls (toggle trace / route) ---
        self.trace_checkbox = QCheckBox("Trace")
        self.trace_checkbox.setChecked(True)
        self.trace_checkbox.stateChanged.connect(lambda _: self.update())

        self.route_checkbox = QCheckBox("Route")
        self.route_checkbox.setChecked(True)
        self.route_checkbox.stateChanged.connect(lambda _: self.update())

        overlay = QWidget(self)
        overlay.setStyleSheet("background-color: rgba(0, 0, 0, 140); border-radius: 4px;" "QCheckBox { color: white; }")
        overlay_layout = QHBoxLayout(overlay)
        overlay_layout.setContentsMargins(6, 2, 6, 2)
        overlay_layout.setSpacing(10)
        overlay_layout.addWidget(self.trace_checkbox)
        overlay_layout.addWidget(self.route_checkbox)
        overlay.move(8, 8)
        overlay.adjustSize()
        self._overlay = overlay

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
        rect = QRectF(self.rect())

        if self.state.has_new_map:
            self.update_map()
            self.state.has_new_map = False

        self._record_trace_point()

        if self._map_pixmap is None:
            painter.fillRect(rect, Qt.GlobalColor.darkGray)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for map...")
            return

        transform = self._compute_view_transform(rect)

        painter.fillRect(rect, BACKGROUND_COLOR)
        self._draw_grid(painter, transform)
        self._draw_map_pixmap(painter, transform)

        if self.route_checkbox.isChecked():
            self._draw_route(painter, transform)

        if self.trace_checkbox.isChecked():
            self._draw_trace(painter, transform)

        self._draw_robot(painter, transform)

    # ------------------------------------------------------------------
    # World <-> screen transform
    # ------------------------------------------------------------------

    def _compute_view_transform(self, rect: QRectF) -> _ViewTransform:
        map_world_w = self._map_width * self._resolution
        map_world_h = self._map_height * self._resolution

        vx_min = self._origin_x - GRID_MARGIN_M
        vx_max = self._origin_x + map_world_w + GRID_MARGIN_M
        vy_min = self._origin_y - GRID_MARGIN_M
        vy_max = self._origin_y + map_world_h + GRID_MARGIN_M

        view_w = max(vx_max - vx_min, 1e-6)
        view_h = max(vy_max - vy_min, 1e-6)
        scale = min(rect.width() / view_w, rect.height() / view_h)

        draw_w = view_w * scale
        draw_h = view_h * scale
        offset_x = rect.x() + (rect.width() - draw_w) / 2.0
        offset_y = rect.y() + (rect.height() - draw_h) / 2.0

        return _ViewTransform(
            scale=scale,
            vx_min=vx_min,
            vx_max=vx_max,
            vy_min=vy_min,
            vy_max=vy_max,
            offset_x=offset_x,
            offset_y=offset_y,
        )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_map_pixmap(self, painter: QPainter, t: _ViewTransform) -> None:
        map_world_w = self._map_width * self._resolution
        map_world_h = self._map_height * self._resolution
        top_left = t.to_screen(self._origin_x, self._origin_y + map_world_h)
        bottom_right = t.to_screen(self._origin_x + map_world_w, self._origin_y)
        draw_rect = QRectF(top_left, bottom_right)
        painter.drawPixmap(draw_rect, self._map_pixmap, QRectF(self._map_pixmap.rect()))

    def _draw_grid(self, painter: QPainter, t: _ViewTransform) -> None:
        if t.scale <= 0:
            return
        spacing = _nice_grid_spacing(t.scale)

        pen = QPen(GRID_COLOR)
        pen.setWidth(1)
        painter.setPen(pen)

        x = math.ceil(t.vx_min / spacing) * spacing
        while x <= t.vx_max:
            painter.drawLine(t.to_screen(x, t.vy_max), t.to_screen(x, t.vy_min))
            x += spacing

        y = math.ceil(t.vy_min / spacing) * spacing
        while y <= t.vy_max:
            painter.drawLine(t.to_screen(t.vx_min, y), t.to_screen(t.vx_max, y))
            y += spacing

        # Scale/dimension labels along the bottom and left edges of the view.
        painter.setPen(GRID_LABEL_COLOR)
        x = math.ceil(t.vx_min / spacing) * spacing
        while x <= t.vx_max:
            p = t.to_screen(x, t.vy_min)
            painter.drawText(QPointF(p.x() + 3, p.y() - 4), f"{x:g}m")
            x += spacing

        y = math.ceil(t.vy_min / spacing) * spacing
        while y <= t.vy_max:
            p = t.to_screen(t.vx_min, y)
            painter.drawText(QPointF(p.x() + 3, p.y() - 4), f"{y:g}m")
            y += spacing

    def _draw_route(self, painter: QPainter, t: _ViewTransform) -> None:
        route = getattr(self.state, "route", None)
        if not route:
            return

        points = [t.to_screen(x, y) for x, y, _ in route]
        if not points:
            return

        pen = QPen(ROUTE_LINE_COLOR)
        pen.setWidthF(ROUTE_LINE_WIDTH_PX)
        painter.setPen(pen)
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ROUTE_POINT_COLOR)
        for p in points:
            painter.drawEllipse(p, ROUTE_POINT_RADIUS_PX, ROUTE_POINT_RADIUS_PX)

    def _record_trace_point(self) -> None:
        pose = self.state.pose
        if not pose:
            return
        x, y = pose["position"]["x"], pose["position"]["y"]
        if self._trace and math.hypot(x - self._trace[-1][0], y - self._trace[-1][1]) < TRACE_MIN_STEP_M:
            return
        self._trace.append((x, y))

    def _draw_trace(self, painter: QPainter, t: _ViewTransform) -> None:
        if len(self._trace) < 2:
            return

        points = [t.to_screen(x, y) for x, y in self._trace]
        pen = QPen(TRACE_COLOR)
        pen.setWidthF(TRACE_WIDTH_PX)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)

    def _draw_robot(self, painter: QPainter, t: _ViewTransform) -> None:
        pose = self.state.pose
        if not pose:
            return

        screen = t.to_screen(pose["position"]["x"], pose["position"]["y"])

        painter.setPen(ROBOT_COLOR)
        painter.setBrush(ROBOT_COLOR)
        painter.drawEllipse(screen, ROBOT_RADIUS_PX, ROBOT_RADIUS_PX)

        # Image y grows downward while yaw is measured counter-clockwise in
        # the map frame (y grows "up"), so negate yaw for the on-screen heading.
        yaw = pose["yaw"]
        heading = QPointF(
            screen.x() + ROBOT_HEADING_LENGTH_PX * math.cos(-yaw),
            screen.y() + ROBOT_HEADING_LENGTH_PX * math.sin(-yaw),
        )
        painter.drawLine(screen, heading)

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_erosion as _scipy_erosion

# ---------------------------------------------------------------------------
# Lightweight, ROS-free grid type. Duck-types the parts of nav_msgs/OccupancyGrid
# that this module needs (.info.resolution/width/height/origin.position.x/y,
# .data), so it can be built and consumed on a machine with no ROS install
# (e.g. topside UI), and converted into a real OccupancyGrid message
# wherever ROS actually is available (e.g. coverage_server).
# ---------------------------------------------------------------------------


@dataclass
class _Position:
    x: float
    y: float


@dataclass
class _Origin:
    position: _Position


@dataclass
class GridInfo:
    resolution: float
    width: int
    height: int
    origin: _Origin


@dataclass
class SimpleGrid:
    info: GridInfo
    data: list = field(default_factory=list)


def build_boundary_grid(width: float, length: float, resolution: float = 0.2) -> SimpleGrid:
    """
    Build a rectangular boundary grid: free space inside a 1-cell-thick
    occupied border. This is the single source of truth for turning
    (boundary width, length) into a grid — call it both when planning a
    route offline and when publishing the matching map, so the two never
    disagree.
    """
    width_cells = math.ceil(width / resolution)
    length_cells = math.ceil(length / resolution)

    data = [0] * (length_cells * width_cells)

    for y in range(width_cells):
        for x in range(length_cells):
            on_border = x == 0 or x == length_cells - 1 or y == 0 or y == width_cells - 1
            if on_border:
                data[y * length_cells + x] = 100

    info = GridInfo(
        resolution=resolution,
        width=length_cells,
        height=width_cells,
        origin=_Origin(position=_Position(x=-length / 2.0, y=-width / 2.0)),
    )
    return SimpleGrid(info=info, data=data)


def _navigable_bbox(map, robot_radius, safety_margin=0.0, roi=None):
    """
    Shared helper: erode free space by (robot_radius + safety_margin) and
    return the bounding box (cell + world coordinates) of the navigable
    region, along with the boolean grid to use for further queries.

    Returns None if the region (after roi clipping) is empty.
    """
    info = map.info
    res = info.resolution
    w, h = info.width, info.height
    ox, oy = info.origin.position.x, info.origin.position.y

    grid = np.array(map.data, dtype=np.int8).reshape((h, w))
    free = grid == 0

    total_clearance = robot_radius + safety_margin
    r_cells = max(1, int(math.ceil(total_clearance / res)))
    struct = np.ones((2 * r_cells + 1, 2 * r_cells + 1), dtype=bool)
    eroded = _scipy_erosion(free, structure=struct)

    rows, cols = np.where(eroded)
    used_eroded = True
    if len(rows) == 0:
        # Erosion killed every cell (region too small/tight) — fall back to
        # raw free space. Clearance is then NOT guaranteed by the grid alone.
        rows, cols = np.where(free)
        used_eroded = False
    if len(rows) == 0:
        return None

    r_min, r_max = int(rows.min()), int(rows.max())
    c_min, c_max = int(cols.min()), int(cols.max())

    if roi is not None:
        rx_min, ry_min, rx_max, ry_max = roi
        c_min = max(c_min, int((rx_min - ox) / res))
        c_max = min(c_max, int((rx_max - ox) / res))
        r_min = max(r_min, int((ry_min - oy) / res))
        r_max = min(r_max, int((ry_max - oy) / res))

    if c_min >= c_max or r_min >= r_max:
        return None

    return dict(
        r_min=r_min,
        r_max=r_max,
        c_min=c_min,
        c_max=c_max,
        nav=eroded if used_eroded else free,
        used_eroded=used_eroded,
        res=res,
        ox=ox,
        oy=oy,
        w=w,
        h=h,
    )


def _row_runs(nav_row, c_min, c_max):
    """
    Find contiguous runs of navigable cells in nav_row[c_min:c_max+1].
    Returns a list of (c_start, c_end) inclusive column-index pairs, one
    per contiguous run. A row with an obstacle in the middle produces two
    (or more) separate runs rather than one run that cuts through it.
    """
    runs = []
    start = None
    for c in range(c_min, c_max + 1):
        navigable = nav_row[c]
        if navigable and start is None:
            start = c
        elif not navigable and start is not None:
            runs.append((start, c - 1))
            start = None
    if start is not None:
        runs.append((start, c_max))
    return runs


def compute_spiral_path(
    map,
    robot_radius: float,
    spacing: float,
    safety_margin: float = 0.0,
    roi: list[float] | None = None,
) -> list[tuple[float, float, float]]:
    """
    Generate the *shape* of an inward rectangular spiral covering the
    navigable region of `map`: a minimal set of (x, y, yaw) waypoints —
    just the straight-segment endpoints and the tangent points where each
    rounded corner begins/ends. No interior arc points are sampled.

    The corner turning radius is derived from robot_radius and spacing
    (max(robot_radius, spacing)) rather than taken as a separate parameter.

    IMPORTANT: this path is NOT kinematically smooth on its own (corners
    are just tangent-point pairs, not curves). Feed the result through a
    kinematically-aware planner — e.g. Nav2's NavigateThroughPoses with the
    SmacPlannerHybrid planner — so it reconstructs the actual rounded
    corner and inserts any reversing needed. Set that planner's
    `minimum_turning_radius` to max(robot_radius, spacing) to match.

    robot_radius: used (with safety_margin) to erode free space so the
        centreline keeps clearance from walls/obstacles, and (with
        spacing) to size the rounded corners.
    roi: optional [x_min, y_min, x_max, y_max] to restrict the region.
    """
    bbox = _navigable_bbox(map, robot_radius, safety_margin, roi)
    if bbox is None:
        print("Region is empty — no waypoints.")
        return []

    res, ox, oy = bbox["res"], bbox["ox"], bbox["oy"]
    r_min, r_max = bbox["r_min"], bbox["r_max"]
    c_min, c_max = bbox["c_min"], bbox["c_max"]
    used_eroded = bbox["used_eroded"]

    # World-space bounding box of the navigable region.
    x_min = ox + c_min * res
    x_max = ox + (c_max + 1) * res
    y_min = oy + r_min * res
    y_max = oy + (r_max + 1) * res

    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0
    length = x_max - x_min  # x-extent
    width = y_max - y_min  # y-extent

    clearance = 0.0 if used_eroded else (robot_radius + safety_margin)
    turning_radius = max(robot_radius, spacing)

    left = -length / 2.0 + clearance
    right = length / 2.0 - clearance
    bottom = -width / 2.0 + clearance
    top = width / 2.0 - clearance

    path: list[tuple[float, float, float]] = []
    first = True

    while right - left > 2.0 * turning_radius and top - bottom > 2.0 * turning_radius:
        r = turning_radius

        if first:
            path.append((left + r, bottom, 0.0))
            first = False

        # Bottom-right corner: straight-edge end (arc entry) -> arc exit tangent.
        path.append((right - r, bottom, 0.0))
        path.append((right, bottom + r, math.pi / 2))

        # Top-right corner.
        path.append((right, top - r, math.pi / 2))
        path.append((right - r, top, math.pi))

        # Top-left corner.
        path.append((left + r, top, math.pi))
        path.append((left, top - r, -math.pi / 2))

        # Bottom-left corner. Its exit tangent is also the entry point for
        # the next (smaller) loop's bottom edge — note the diagonal "step
        # inward" this implies once left/right/bottom/top update below.
        path.append((left, bottom + r, -math.pi / 2))
        path.append((left + r, bottom, 0.0))

        left += spacing
        right -= spacing
        bottom += spacing
        top -= spacing

    # Translate from the rectangle's centered local frame into world coordinates.
    return [(x + center_x, y + center_y, yaw) for (x, y, yaw) in path]


def compute_boustrophedon_path(
    map,
    robot_radius: float,
    spacing: float,
    safety_margin: float = 0.0,
    roi: list[float] | None = None,
) -> list[tuple[float, float, float]]:
    """
    Generate a boustrophedon (back-and-forth sweep) path covering the
    navigable region of `map`: a minimal set of (x, y, yaw) waypoints —
    just the endpoints of each contiguous navigable run on each sweep
    line. A row split by an obstacle produces two separate runs (and thus
    a gap between their waypoints) rather than one waypoint pair that
    implies a straight line through the obstacle.

    IMPORTANT: there is no connecting geometry between the end of one row
    and the start of the next (or between separate runs within a row) —
    that U-turn / detour must be generated by a downstream kinematically-
    aware planner, e.g. Nav2's NavigateThroughPoses with SmacPlannerHybrid
    (motion_model_for_search: REEDS_SHEPP, so it can reverse).

    robot_radius / safety_margin: combined to erode free space so the path
        keeps clearance from walls/obstacles (see _navigable_bbox).
    roi: optional [x_min, y_min, x_max, y_max] to restrict the region.
    """
    bbox = _navigable_bbox(map, robot_radius, safety_margin, roi)
    if bbox is None:
        print("Region is empty — no waypoints.")
        return []

    res, ox, oy = bbox["res"], bbox["ox"], bbox["oy"]
    r_min, r_max = bbox["r_min"], bbox["r_max"]
    c_min, c_max = bbox["c_min"], bbox["c_max"]
    nav = bbox["nav"]

    spacing_cells = max(1, int(round(spacing / res)))
    waypoints: list[tuple[float, float, float]] = []

    row = r_min
    left_to_right = True
    while row <= r_max:
        runs = _row_runs(nav[row], c_min, c_max)

        if not left_to_right:
            runs = list(reversed(runs))

        for c0, c1 in runs:
            if not left_to_right:
                c0, c1 = c1, c0  # traverse this run right-to-left too

            wy = oy + (row + 0.5) * res
            yaw = 0.0 if left_to_right else math.pi

            waypoints.append((ox + (c0 + 0.5) * res, wy, yaw))
            if c0 != c1:
                waypoints.append((ox + (c1 + 0.5) * res, wy, yaw))

        left_to_right = not left_to_right
        row += spacing_cells

    return waypoints

"""
Road connectivity — determines whether a plot has road access.

A plot is road-accessible if it or any adjacent plot (4-connected)
is a road segment endpoint.
"""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.world import World
from realm.world.plot_scale import (
    CELLS_PER_WORLD_TILE,
    cells_occupied,
    plot_deed_grid_cells,
    plot_world_cells_tuple,
    plot_world_span,
)
from realm.world.world import Plot

ROAD_EXEMPT_RECIPES: frozenset[str] = frozenset({
    "hand_mine_coal",
    "hand_mine_ore",
    "hand_dig_clay",
    "hand_mine_sulfur",
    "hand_mine_tin",
    "fishing",
    "gather_herbs",
    "grow_grain",
    "coal_generator",
    "tidal_power",
})

ROAD_EXEMPT_BLUEPRINTS: frozenset[str] = frozenset({
    "residence",
    "store",
    "waystation",
})

ROAD_REQUIREMENT_GRACE_TICKS: int = 43_200

_endpoint_cache: dict[int, set[str]] = {}


def _get_road_endpoints(world: World) -> set[str]:
    key = id(world.road_segments)
    if key in _endpoint_cache:
        return _endpoint_cache[key]
    endpoints: set[str] = set()
    for seg in world.road_segments:
        endpoints.add(str(seg.from_plot))
        endpoints.add(str(seg.to_plot))
    if len(_endpoint_cache) > 5:
        _endpoint_cache.clear()
    _endpoint_cache[key] = endpoints
    return endpoints


def invalidate_road_cache() -> None:
    _endpoint_cache.clear()


def _footprint_cells_on_plot(
    world: World, plot_id: str, blueprint_id: str, grid_x: int, grid_y: int
) -> set[tuple[int, int]]:
    bp = world.blueprints.get(blueprint_id)
    fw = int(bp.footprint_w) if bp is not None else 1
    fh = int(bp.footprint_h) if bp is not None else 1
    return set(cells_occupied(int(grid_x), int(grid_y), fw, fh))


def grid_cell_world_xy(plot: Plot, gx: int, gy: int) -> tuple[int, int] | None:
    """World map tile (wx, wy) containing build cell (gx, gy)."""
    deed = plot_deed_grid_cells(plot)
    if (gx, gy) not in deed:
        return None
    min_x, min_y, _, _ = plot_world_span(plot)
    cells = set(plot_world_cells_tuple(plot))
    tile_ix = gx // CELLS_PER_WORLD_TILE
    tile_iy = gy // CELLS_PER_WORLD_TILE
    wx = min_x + tile_ix
    wy = min_y + tile_iy
    if (wx, wy) in cells:
        return wx, wy
    return None


def _site_road_cells(world: World, plot_id: str) -> set[tuple[int, int]]:
    road_cells: set[tuple[int, int]] = set()
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) != plot_id or str(pb.status) not in ("active", "construction"):
            continue
        if str(pb.blueprint_id) != "road_segment":
            continue
        road_cells |= _footprint_cells_on_plot(
            world, plot_id, "road_segment", int(pb.grid_x), int(pb.grid_y)
        )
    return road_cells


def plot_site_roads_link_world(world: World, plot_id: PlotId) -> bool:
    """Site road graph touches a neighbor plot on the world road network."""
    if is_road_accessible(world, plot_id):
        return True
    plot = world.plots.get(plot_id)
    if plot is None:
        return False
    road_cells = _site_road_cells(world, str(plot_id))
    if not road_cells:
        return False
    deed = plot_deed_grid_cells(plot)
    for gx, gy in road_cells:
        wxwy = grid_cell_world_xy(plot, gx, gy)
        if wxwy is None:
            continue
        wx, wy = wxwy
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            if (gx + dx, gy + dy) in deed:
                continue
            neighbor = PlotId(f"p-{wx + dx}-{wy + dy}")
            if is_road_accessible(world, neighbor):
                return True
    return False


def plot_world_link_edges(world: World, plot_id: PlotId) -> list[dict[str, object]]:
    """Deed-boundary cells where a world road can connect to an adjacent plot."""
    from realm.infrastructure.roads import find_segment_between

    plot = world.plots.get(plot_id)
    if plot is None:
        return []
    pid = str(plot_id)
    deed = plot_deed_grid_cells(plot)
    if not deed:
        return []
    road_cells = _site_road_cells(world, pid)
    out: list[dict[str, object]] = []
    seen: set[tuple[int, int, str]] = set()
    for gx, gy in sorted(deed):
        wxwy = grid_cell_world_xy(plot, gx, gy)
        if wxwy is None:
            continue
        wx, wy = wxwy
        for dx, dy, direction in (
            (0, -1, "north"),
            (0, 1, "south"),
            (-1, 0, "west"),
            (1, 0, "east"),
        ):
            if (gx + dx, gy + dy) in deed:
                continue
            key = (gx, gy, direction)
            if key in seen:
                continue
            seen.add(key)
            neighbor_id = PlotId(f"p-{wx + dx}-{wy + dy}")
            if world.plots.get(neighbor_id) is None:
                continue
            seg = find_segment_between(world, plot_id, neighbor_id)
            out.append(
                {
                    "grid_x": gx,
                    "grid_y": gy,
                    "direction": direction,
                    "neighbor_plot_id": str(neighbor_id),
                    "segment_exists": seg is not None,
                    "neighbor_road_access": is_road_accessible(world, neighbor_id),
                    "site_road_here": (gx, gy) in road_cells,
                }
            )
    return out


def plot_site_roads_connect_workshops(world: World, plot_id: PlotId) -> bool:
    """True when each non-exempt workshop has at least one cell beside a site road cell."""
    pid = str(plot_id)
    road_cells: set[tuple[int, int]] = set()
    workshops: list[set[tuple[int, int]]] = []
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) != pid:
            continue
        if str(pb.status) not in ("active", "construction"):
            continue
        bid = str(pb.blueprint_id)
        cells = _footprint_cells_on_plot(world, pid, bid, int(pb.grid_x), int(pb.grid_y))
        if bid == "road_segment":
            road_cells |= cells
        elif bid in ROAD_EXEMPT_BLUEPRINTS:
            continue
        else:
            workshops.append(cells)
    if not workshops:
        return False
    if not road_cells:
        return False
    for footprint in workshops:
        connected = False
        for cx, cy in footprint:
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                if (cx + dx, cy + dy) in road_cells or (cx, cy) in road_cells:
                    connected = True
                    break
            if connected:
                break
        if not connected:
            return False
    return True


def is_road_accessible(world: World, plot_id: PlotId) -> bool:
    endpoints = _get_road_endpoints(world)
    pid_str = str(plot_id)

    if pid_str in endpoints:
        return True

    parts = pid_str.split("-")
    if len(parts) < 3:
        return False
    try:
        x, y = int(parts[-2]), int(parts[-1])
    except ValueError:
        return False

    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        neighbour = f"p-{x + dx}-{y + dy}"
        if neighbour in endpoints:
            return True

    return False


def require_road_access(
    world: World,
    plot_id: PlotId,
    recipe_id: str,
    blueprint_id: str | None = None,
) -> dict[str, bool | str] | None:
    if int(world.tick) < ROAD_REQUIREMENT_GRACE_TICKS:
        return None

    if recipe_id in ROAD_EXEMPT_RECIPES:
        return None

    if blueprint_id and blueprint_id in ROAD_EXEMPT_BLUEPRINTS:
        return None

    for row in world.plot_buildings:
        if str(row.get("plot_id", "")) == str(plot_id):
            if str(row.get("build_mode", "")) == "bootstrap":
                return None

    if is_road_accessible(world, plot_id):
        return None
    if plot_site_roads_connect_workshops(world, plot_id):
        return None

    return {
        "ok": False,
        "reason": (
            "this plot has no road access — connect workshops to site roads "
            "(road_segment on the build grid) or to the world road network on "
            "an adjacent plot edge, or use hand-labour recipes."
        ),
    }

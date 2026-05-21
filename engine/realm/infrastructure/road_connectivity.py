"""
Road connectivity — determines whether a plot has road access.

A plot is road-accessible if it or any adjacent plot (4-connected)
is a road segment endpoint.
"""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.world import World
from realm.world.plot_scale import cells_occupied

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

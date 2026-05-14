"""Phase 7A — Genesis four-island world geometry.

In the Genesis scenario the world is four landmasses separated by deep
ocean. Ocean tiles (``terrain == WATER_DEEP``) are **impassable by land
movement** (``tile_movement_cost == math.inf``) and shipping across them
costs **2×** the normal per-tile rate. Each plot is tagged with an
``island_id`` in ``[0, 3]`` when it sits on land, and is omitted from the
mapping when it is ocean. The mapping is computed once at bootstrap (after
plots are generated) and cached in ``world.scenario_state["plot_islands"]``
as ``{plot_id_str: island_id_int}``.

Non-genesis worlds have no islands; helpers degrade to "single landmass" /
``island_id is None`` so legacy callers keep working unchanged.
"""

from __future__ import annotations

import math

from realm.core.ids import PlotId
from realm.world.terrain import Terrain
from realm.world import World


__all__ = [
    "is_ocean_terrain",
    "is_ocean_plot",
    "tile_movement_cost",
    "plot_island_id",
    "is_inter_island_shipment",
    "compute_plot_islands",
    "island_coastal_plot_ids",
]


def is_ocean_terrain(terrain: Terrain) -> bool:
    """``True`` when this terrain is deep ocean (impassable by land)."""
    return terrain == Terrain.WATER_DEEP


def is_ocean_plot(world: World, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    if p is None:
        return False
    return is_ocean_terrain(p.terrain)


def tile_movement_cost(world: World, plot_id: PlotId) -> float:
    """Land-movement cost for traversing this plot.

    Ocean tiles return ``math.inf`` (impassable). All other terrains are
    passable at uniform cost ``1.0``; terrain-specific movement multipliers
    (mountain slowdown, swamp drag, etc.) can be layered on later without
    changing the impassable-ocean contract this function guarantees.
    """
    if is_ocean_plot(world, plot_id):
        return math.inf
    return 1.0


def plot_island_id(world: World, plot_id: PlotId) -> int | None:
    """Which island this plot belongs to, or ``None`` for ocean / non-island worlds."""
    islands_map = world.scenario_state.get("plot_islands")
    if not isinstance(islands_map, dict):
        return None
    val = islands_map.get(str(plot_id))
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def is_inter_island_shipment(
    world: World, from_plot_id: PlotId, to_plot_id: PlotId
) -> bool:
    """``True`` when origin and destination sit on *different* land islands.

    Returns ``False`` for intra-island shipments, for shipments where either
    endpoint is ocean (those will already fail upstream because plots must be
    owned), and for non-island worlds (no ``plot_islands`` mapping cached).
    """
    fi = plot_island_id(world, from_plot_id)
    ti = plot_island_id(world, to_plot_id)
    return fi is not None and ti is not None and fi != ti


def compute_plot_islands(world: World) -> dict[str, int]:
    """Connected components of non-ocean plots in the 4-neighbourhood grid.

    Components are sorted by their bounding-box top-left ``(min_y, min_x)`` so
    ``island_id`` is deterministic across the same seed. Ocean plots are not
    included in the returned mapping (callers treat the ``None`` lookup as
    "ocean / no land identity").

    Used at bootstrap once; not called on a hot path. O(N) where N is land
    plots (Union-find would be faster but DFS is fine at our scale).
    """
    coord_to_plot: dict[tuple[int, int], str] = {}
    for pid, p in world.plots.items():
        if is_ocean_terrain(p.terrain):
            continue
        coord_to_plot[(int(p.x), int(p.y))] = str(pid)

    visited: set[tuple[int, int]] = set()
    components: list[list[tuple[int, int]]] = []
    for start in sorted(coord_to_plot.keys()):
        if start in visited:
            continue
        comp: list[tuple[int, int]] = []
        stack: list[tuple[int, int]] = [start]
        while stack:
            cur = stack.pop()
            if cur in visited or cur not in coord_to_plot:
                continue
            visited.add(cur)
            comp.append(cur)
            x, y = cur
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in coord_to_plot and (nx, ny) not in visited:
                    stack.append((nx, ny))
        components.append(comp)

    components.sort(key=lambda c: (min(p[1] for p in c), min(p[0] for p in c)))
    out: dict[str, int] = {}
    for idx, comp in enumerate(components):
        for x, y in comp:
            out[coord_to_plot[(x, y)]] = idx
    return out


def island_coastal_plot_ids(world: World, island_id: int) -> list[str]:
    """Plot ids on ``island_id`` that touch ocean — eligible for docks/ports.

    A coastal plot is a land plot with at least one 4-neighbour that is
    either deep water or off the map edge (the map border counts as "ocean"
    for the purposes of coastal docking).
    """
    coord_to_plot: dict[tuple[int, int], str] = {}
    for pid, p in world.plots.items():
        coord_to_plot[(int(p.x), int(p.y))] = str(pid)
    ocean_coords: set[tuple[int, int]] = {
        c for c, pid_s in coord_to_plot.items()
        if is_ocean_terrain(world.plots[PlotId(pid_s)].terrain)
    }
    islands_map = world.scenario_state.get("plot_islands") or {}
    out: list[str] = []
    for pid_s, isl in islands_map.items():
        if int(isl) != int(island_id):
            continue
        p = world.plots.get(PlotId(pid_s))
        if p is None:
            continue
        x, y = int(p.x), int(p.y)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in ocean_coords or (nx, ny) not in coord_to_plot:
                out.append(pid_s)
                break
    return sorted(out)

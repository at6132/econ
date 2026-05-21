"""Genesis starter road networks — cross-shaped town grids at bootstrap."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from realm.core.ids import PartyId, PlotId
from realm.infrastructure.road_connectivity import invalidate_road_cache
from realm.infrastructure.roads import find_segment_between
from realm.production.decay import BUILDING_CONDITION_FULL_BPS
from realm.world import RoadSegment

if TYPE_CHECKING:
    from realm.population.towns import Town
    from realm.world import World

GENESIS_ROADS_PARTY: PartyId = PartyId("genesis_settlement")
_CARDINAL_STEPS: int = 3
_ROAD_SEGMENT_BLUEPRINT: str = "road_segment"


def _is_water(plot: object) -> bool:
    return str(getattr(plot, "terrain", "")).lower().startswith("water")


def _geographic_neighbors(world: World, plot_id: PlotId) -> list[PlotId]:
    """Plots whose deed center is Manhattan-1 from ``plot_id`` (sparse maps)."""
    plot = world.plots.get(plot_id)
    if plot is None:
        return []
    px, py = int(plot.x), int(plot.y)
    out: list[PlotId] = []
    for other in world.plots.values():
        if other.plot_id == plot_id:
            continue
        if abs(int(other.x) - px) + abs(int(other.y) - py) != 1:
            continue
        if _is_water(other):
            continue
        out.append(other.plot_id)
    out.sort(key=str)
    return out


def _shortest_plot_path(
    world: World, start: PlotId, end: PlotId, *, max_depth: int = 48
) -> list[PlotId]:
    if str(start) == str(end):
        return [start]
    queue: deque[tuple[PlotId, list[PlotId]]] = deque([(start, [start])])
    seen: set[str] = {str(start)}
    while queue:
        pid, path = queue.popleft()
        if len(path) > max_depth:
            continue
        for adj in _geographic_neighbors(world, pid):
            key = str(adj)
            if key in seen:
                continue
            if adj == end:
                return path + [adj]
            seen.add(key)
            queue.append((adj, path + [adj]))
    return []


def _append_bootstrap_segment(
    world: World, from_plot: PlotId, to_plot: PlotId, owner: PartyId
) -> bool:
    if find_segment_between(world, from_plot, to_plot) is not None:
        return False
    from realm.infrastructure.roads import _are_adjacent

    if not _are_adjacent(world, from_plot, to_plot):
        return False
    world.next_road_segment_seq += 1
    sid = f"road-{world.next_road_segment_seq}"
    world.road_segments.append(
        RoadSegment(
            segment_id=sid,
            from_plot=PlotId(str(from_plot)),
            to_plot=PlotId(str(to_plot)),
            owner=owner,
            built_at_tick=0,
            toll_rate_pct=0,
            condition_bps=BUILDING_CONDITION_FULL_BPS,
            last_maintenance_tick=0,
        )
    )
    return True


def _link_path(world: World, path: list[PlotId], owner: PartyId) -> int:
    built = 0
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        if _append_bootstrap_segment(world, a, b, owner):
            place_genesis_road_cell(world, str(a), owner)
            place_genesis_road_cell(world, str(b), owner)
            built += 1
    return built


def place_genesis_road_cell(world: World, plot_id_str: str, party: PartyId) -> None:
    """Place one active ``road_segment`` cell on a plot (bootstrap, no cost)."""
    from realm.production.blueprints import seed_world_blueprints
    from realm.world.placed_buildings import PlacedBuilding, register_placed_building

    if _road_segment_on_plot(world, plot_id_str):
        return
    if _ROAD_SEGMENT_BLUEPRINT not in world.blueprints:
        seed_world_blueprints(world)
    bp = world.blueprints.get(_ROAD_SEGMENT_BLUEPRINT)
    if bp is None:
        return
    from realm.actions.blueprint_actions import _find_free_position

    pos = _find_free_position(world, plot_id_str, bp)
    if pos is None:
        return
    gx, gy = pos
    world.next_building_instance_seq += 1
    iid = f"pb_{world.next_building_instance_seq:06d}"
    due = int(bp.maintenance_interval_ticks) if int(bp.maintenance_interval_ticks) > 0 else 7200
    pb = PlacedBuilding(
        instance_id=iid,
        blueprint_id=_ROAD_SEGMENT_BLUEPRINT,
        plot_id=plot_id_str,
        grid_x=int(gx),
        grid_y=int(gy),
        built_at_tick=0,
        built_by=str(party),
        status="active",
        efficiency_pct=100,
        missed_maintenance_cycles=0,
        due_at_tick=due,
        original_cost_cents=0,
        book_value_cents=0,
    )
    register_placed_building(world, pb)
    world.building_maintenance[iid] = {
        "due_at_tick": due,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }


def _road_segment_on_plot(world: World, plot_id_str: str) -> bool:
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) == plot_id_str and pb.blueprint_id == _ROAD_SEGMENT_BLUEPRINT:
            return True
    return False


def _step_cardinal(world: World, current: PlotId, dx: int, dy: int) -> PlotId | None:
    """One geographic step from ``current`` toward ``(dx, dy)``."""
    plot = world.plots.get(current)
    if plot is None:
        return None
    target_x = int(plot.x) + int(dx)
    target_y = int(plot.y) + int(dy)
    best: PlotId | None = None
    best_d = 10_000
    for adj in _geographic_neighbors(world, current):
        other = world.plots.get(adj)
        if other is None:
            continue
        d = abs(int(other.x) - target_x) + abs(int(other.y) - target_y)
        if d < best_d:
            best_d = d
            best = adj
    return best


def seed_town_roads(world: World, town: Town) -> int:
    """Plant a minimal road cross at ``town`` center and link stores. Returns segments added."""
    owner = GENESIS_ROADS_PARTY
    if world.plots.get(town.center_plot) is None:
        return 0
    built = 0
    place_genesis_road_cell(world, str(town.center_plot), owner)

    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        current = town.center_plot
        for _ in range(_CARDINAL_STEPS):
            nxt = _step_cardinal(world, current, dx, dy)
            if nxt is None:
                break
            if _append_bootstrap_segment(world, current, nxt, owner):
                place_genesis_road_cell(world, str(current), owner)
                place_genesis_road_cell(world, str(nxt), owner)
                built += 1
            current = nxt

    for store_pid in town.store_plots:
        path = _shortest_plot_path(world, store_pid, town.center_plot)
        if path:
            built += _link_path(world, path, owner)

    return built


def seed_genesis_town_roads(world: World) -> int:
    """Seed starter roads for every genesis town. Returns total new segments."""
    total = 0
    for town in world.towns.values():
        total += seed_town_roads(world, town)
    invalidate_road_cache()
    return total

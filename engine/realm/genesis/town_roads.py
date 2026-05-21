"""Genesis starter road networks — cross-shaped town grids at bootstrap."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from realm.core.ids import PartyId, PlotId
from realm.infrastructure.road_connectivity import invalidate_road_cache
from realm.infrastructure.roads import find_segment_between
from realm.production.decay import BUILDING_CONDITION_FULL_BPS
from realm.world import RoadSegment
from realm.world.geo import manhattan

if TYPE_CHECKING:
    from realm.population.towns import Town
    from realm.world import World

GENESIS_ROADS_PARTY: PartyId = PartyId("genesis_settlement")
_CARDINAL_STEPS: int = 6
_CARDINAL_SNAP_RADIUS: int = 6
_MAX_GENESIS_ROAD_SPAN: int = 6
_INTER_TOWN_MAX_DISTANCE: int = 80
_ROAD_SEGMENT_BLUEPRINT: str = "road_segment"
_POWER_SHED_BLUEPRINT: str = "power_shed"

_coord_index: dict[tuple[int, int], PlotId] = {}


def _build_coord_index(world: World) -> None:
    """Build (x, y) → PlotId lookup. Call once per bootstrap."""
    global _coord_index
    _coord_index = {
        (int(p.x), int(p.y)): p.plot_id
        for p in world.plots.values()
        if not _is_water(p)
    }


def _is_water(plot: object) -> bool:
    return str(getattr(plot, "terrain", "")).lower().startswith("water")


def _geographic_neighbors(world: World, plot_id: PlotId) -> list[PlotId]:
    """O(1) neighbor lookup — plot centers one world tile apart."""
    if not _coord_index:
        _build_coord_index(world)
    plot = world.plots.get(plot_id)
    if plot is None:
        return []
    px, py = int(plot.x), int(plot.y)
    result: list[PlotId] = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nbr = _coord_index.get((px + dx, py + dy))
        if nbr is not None:
            result.append(nbr)
    result.sort(key=str)
    return result


def _genesis_linkable(world: World, a: PlotId, b: PlotId) -> bool:
    """Bootstrap-only road span — sparse maps may lack Manhattan-1 deed pairs."""
    d = manhattan(world, a, b)
    return 1 <= d <= _MAX_GENESIS_ROAD_SPAN


def _shortest_plot_path(
    world: World,
    start: PlotId,
    end: PlotId,
    *,
    max_depth: int = 48,
    allowed: set[str] | None = None,
) -> list[PlotId]:
    if str(start) == str(end):
        return [start]
    queue: deque[tuple[PlotId, list[PlotId]]] = deque([(start, [start])])
    seen: set[str] = {str(start)}
    while queue:
        pid, path = queue.popleft()
        if len(path) > max_depth:
            continue
        for adj in _genesis_path_neighbors(world, pid, allowed):
            key = str(adj)
            if key in seen:
                continue
            if adj == end:
                return path + [adj]
            seen.add(key)
            queue.append((adj, path + [adj]))
    return []


def _genesis_path_neighbors(
    world: World, plot_id: PlotId, allowed: set[str] | None
) -> list[PlotId]:
    out: list[PlotId] = list(_geographic_neighbors(world, plot_id))
    if allowed is None:
        return out
    pid_s = str(plot_id)
    for other in allowed:
        if other == pid_s:
            continue
        if _genesis_linkable(world, plot_id, PlotId(other)):
            out.append(PlotId(other))
    seen: set[str] = set()
    unique: list[PlotId] = []
    for p in out:
        k = str(p)
        if k in seen:
            continue
        seen.add(k)
        unique.append(p)
    unique.sort(key=str)
    return unique


def _append_bootstrap_segment(
    world: World, from_plot: PlotId, to_plot: PlotId, owner: PartyId
) -> bool:
    if find_segment_between(world, from_plot, to_plot) is not None:
        return False
    if not _genesis_linkable(world, from_plot, to_plot):
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
    """One step toward ``(dx, dy)`` — snaps across sparse gaps up to snap radius."""
    if not _coord_index:
        _build_coord_index(world)
    plot = world.plots.get(current)
    if plot is None:
        return None
    px, py = int(plot.x), int(plot.y)
    for dist in range(1, _CARDINAL_SNAP_RADIUS + 1):
        nbr = _coord_index.get((px + dx * dist, py + dy * dist))
        if nbr is not None and nbr != current:
            return nbr
    return None


def _town_plot_ids(town: Town) -> list[PlotId]:
    seen: set[str] = set()
    out: list[PlotId] = []
    for pid in (town.center_plot, *town.residential_plots, *town.store_plots):
        key = str(pid)
        if key in seen:
            continue
        seen.add(key)
        out.append(PlotId(key))
    return out


def _connect_town_cluster(world: World, town: Town, owner: PartyId) -> int:
    """Link all town plots when sparse maps have no Manhattan-1 deed pairs."""
    plots = _town_plot_ids(town)
    if not plots:
        return 0
    allowed = {str(p) for p in plots}
    center = str(town.center_plot)
    if center not in allowed:
        return 0
    connected: set[str] = {center}
    unconnected = allowed - connected
    built = 0
    while unconnected:
        best_pair: tuple[str, str] | None = None
        best_dist = _MAX_GENESIS_ROAD_SPAN + 1
        for c in connected:
            for u in unconnected:
                d = manhattan(world, PlotId(c), PlotId(u))
                if d < best_dist:
                    best_dist = d
                    best_pair = (c, u)
        if best_pair is None or best_dist > _MAX_GENESIS_ROAD_SPAN:
            break
        start_s, end_s = best_pair
        path = _shortest_plot_path(
            world,
            PlotId(start_s),
            PlotId(end_s),
            max_depth=24,
            allowed=allowed,
        )
        if not path:
            path = [PlotId(start_s), PlotId(end_s)]
        built += _link_path(world, path, owner)
        connected.add(end_s)
        unconnected.discard(end_s)
    return built


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

    allowed = {str(p) for p in _town_plot_ids(town)}
    for store_pid in town.store_plots:
        path = _shortest_plot_path(
            world, store_pid, town.center_plot, max_depth=48, allowed=allowed
        )
        if path:
            built += _link_path(world, path, owner)

    built += _connect_town_cluster(world, town, owner)
    return built


def _same_island_town_pairs(world: World) -> list[tuple[Town, Town]]:
    """Return pairs of towns on the same island, sorted by center distance."""
    towns = list(world.towns.values())
    pairs: list[tuple[int, Town, Town]] = []
    for i, t1 in enumerate(towns):
        for t2 in towns[i + 1 :]:
            if t1.island_id != t2.island_id:
                continue
            p1 = world.plots.get(t1.center_plot)
            p2 = world.plots.get(t2.center_plot)
            if p1 is None or p2 is None:
                continue
            dist = abs(int(p1.x) - int(p2.x)) + abs(int(p1.y) - int(p2.y))
            pairs.append((dist, t1, t2))
    pairs.sort(key=lambda x: x[0])
    return [(t1, t2) for dist, t1, t2 in pairs if dist <= _INTER_TOWN_MAX_DISTANCE]


def seed_inter_town_roads(world: World) -> int:
    """Connect adjacent same-island towns with a road corridor. Returns segments built."""
    owner = GENESIS_ROADS_PARTY
    built = 0
    for t1, t2 in _same_island_town_pairs(world):
        path = _shortest_plot_path(world, t1.center_plot, t2.center_plot, max_depth=60)
        if path:
            built += _link_path(world, path, owner)
    return built


def seed_genesis_power_sheds(world: World) -> int:
    """
    For each town, place a completed power_shed on a road-connected plot so the
    regional grid has generation from day 1.
    """
    from realm.actions.blueprint_actions import _find_free_position
    from realm.infrastructure.road_connectivity import is_road_accessible
    from realm.production.blueprints import seed_world_blueprints
    from realm.world.placed_buildings import PlacedBuilding, register_placed_building

    seed_world_blueprints(world)
    owner = GENESIS_ROADS_PARTY
    placed = 0
    bp = world.blueprints.get(_POWER_SHED_BLUEPRINT)
    if bp is None:
        return 0

    for town in world.towns.values():
        target_pid: PlotId | None = None
        candidates = [town.center_plot, *town.residential_plots[:10]]
        for pid in candidates:
            plot = world.plots.get(PlotId(str(pid)))
            if plot is None or _is_water(plot):
                continue
            if not is_road_accessible(world, PlotId(str(pid))):
                continue
            has_shed = any(
                pb.blueprint_id == _POWER_SHED_BLUEPRINT and str(pb.plot_id) == str(pid)
                for pb in world.placed_buildings.values()
            )
            if has_shed:
                target_pid = PlotId(str(pid))
                break
            if _find_free_position(world, str(pid), bp) is not None:
                target_pid = PlotId(str(pid))
                break

        if target_pid is None:
            continue

        pos = _find_free_position(world, str(target_pid), bp)
        if pos is None:
            continue
        gx, gy = pos

        world.next_building_instance_seq += 1
        iid = f"pb_{world.next_building_instance_seq:06d}"
        due = int(bp.maintenance_interval_ticks) if int(bp.maintenance_interval_ticks) > 0 else 14_400
        pb_row = PlacedBuilding(
            instance_id=iid,
            blueprint_id=_POWER_SHED_BLUEPRINT,
            plot_id=str(target_pid),
            grid_x=gx,
            grid_y=gy,
            built_at_tick=0,
            built_by=str(owner),
            status="active",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=due,
            original_cost_cents=0,
            book_value_cents=0,
        )
        register_placed_building(world, pb_row)
        world.building_maintenance[iid] = {
            "due_at_tick": due,
            "missed_cycles": 0,
            "efficiency_pct": 100,
        }
        placed += 1

    return placed


def seed_genesis_town_roads(world: World) -> int:
    """Seed starter roads for every genesis town. Returns total new segments."""
    _build_coord_index(world)
    total = 0
    for town in world.towns.values():
        total += seed_town_roads(world, town)
    total += seed_inter_town_roads(world)
    invalidate_road_cache()
    sheds = seed_genesis_power_sheds(world)
    if sheds > 0:
        world.scenario_state["genesis_power_sheds"] = int(sheds)
    return total

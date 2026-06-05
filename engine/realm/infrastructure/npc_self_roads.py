"""NPC-owned plots: build road segments so workshops can pass ``require_road_access``.

Frontier Roads Co. still builds region-scale corridors for profit; this module
covers **party-local** connectivity (settlers, specialists, etc.) on Genesis.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.infrastructure.road_connectivity import (
    ROAD_PREP_LEAD_TICKS,
    ROAD_REQUIREMENT_GRACE_TICKS,
    is_road_accessible,
)
from realm.infrastructure.roads import BUILD_COST_CENTS, BUILD_MATERIALS, build_road, find_segment_between
from realm.world import World

# Production workshops (matches ``realm.agents.genesis_settlers``).
_WORKSHOP_BUILDING_IDS: frozenset[str] = frozenset(
    {
        "strip_mine",
        "timber_yard",
        "grain_row",
        "power_shed",
        "wood_shop",
        "gristmill",
        "kiln_shed",
        "foundry",
        "stone_works",
        "assay_lab",
        "blast_furnace",
        "chemical_works",
        "forge_press",
        "machine_shop",
        "tool_workshop",
    }
)

_SKIP_PARTIES: frozenset[str] = frozenset(
    {
        "player",
        "frontier_roads",
    }
)

_BFS_MAX_DEPTH: int = 32
_MAX_BUILDS_PER_PARTY_PER_DAY: int = 2

BuyFn = Callable[[World, PartyId, MaterialId, int], dict[str, Any]]


def _game_day(world: World) -> int:
    return int(world.tick) // int(TICKS_PER_GAME_DAY)


def _party_skipped(party: PartyId) -> bool:
    s = str(party)
    if s in _SKIP_PARTIES:
        return True
    if s.startswith("t1_") or s.startswith("pop_hub"):
        return True
    return False


def _plot_at_xy(world: World, x: int, y: int) -> PlotId | None:
    pid = PlotId(f"p-{x}-{y}")
    if pid in world.plots:
        return pid
    for cand, plot in world.plots.items():
        if plot.x == x and plot.y == y:
            return cand
    return None


def _adjacent_plot_ids(world: World, plot_id: PlotId) -> list[PlotId]:
    plot = world.plots.get(plot_id)
    if plot is None:
        return []
    out: list[PlotId] = []
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        adj = _plot_at_xy(world, plot.x + dx, plot.y + dy)
        if adj is not None:
            out.append(adj)
    return out


def _bfs_steps_to_road_network(world: World, start: PlotId) -> int:
    """Steps from ``start`` to any road-accessible plot; ``-1`` if not found."""
    if is_road_accessible(world, start):
        return 0
    seen: set[str] = {str(start)}
    queue: deque[tuple[PlotId, int]] = deque([(start, 0)])
    while queue:
        pid, depth = queue.popleft()
        if depth >= _BFS_MAX_DEPTH:
            continue
        for adj in _adjacent_plot_ids(world, pid):
            key = str(adj)
            if key in seen:
                continue
            seen.add(key)
            if is_road_accessible(world, adj):
                return depth + 1
            queue.append((adj, depth + 1))
    return -1


def plot_has_road_required_workshop(world: World, party: PartyId, plot_id: PlotId) -> bool:
    """Completed non-bootstrap workshop on ``plot_id`` owned by ``party``."""
    pid_s = str(plot_id)
    party_s = str(party)
    tick_now = int(world.tick)
    for row in world.plot_buildings:
        if str(row.get("plot_id", "")) != pid_s:
            continue
        if str(row.get("party", "")) != party_s:
            continue
        if str(row.get("build_mode", "")) == "bootstrap":
            continue
        bid = str(row.get("building_id", ""))
        if bid not in _WORKSHOP_BUILDING_IDS:
            continue
        completes = int(row.get("completes_at_tick", 0))
        if completes > tick_now:
            continue
        return True
    return False


def plot_needs_road_access(world: World, party: PartyId, plot_id: PlotId) -> bool:
    if _party_skipped(party):
        return False
    if not plot_has_road_required_workshop(world, party, plot_id):
        return False
    if is_road_accessible(world, plot_id):
        return False
    prep_start = ROAD_REQUIREMENT_GRACE_TICKS - ROAD_PREP_LEAD_TICKS
    if int(world.tick) < prep_start:
        return False
    return True


def _can_afford_road_build(world: World, party: PartyId) -> bool:
    if world.ledger.balance(party_cash_account(party)) < BUILD_COST_CENTS:
        return False
    for mat, need in BUILD_MATERIALS.items():
        if world.inventory.qty(party, mat) < need:
            return False
    return True


def ensure_road_build_supplies(
    world: World,
    party: PartyId,
    *,
    buy_material: BuyFn | None = None,
) -> bool:
    """Top up lumber/stone via market when ``buy_material`` is provided."""
    if _can_afford_road_build(world, party):
        return True
    if buy_material is None:
        return False
    for mat, need in BUILD_MATERIALS.items():
        short = int(need) - int(world.inventory.qty(party, mat))
        if short <= 0:
            continue
        r = buy_material(world, party, mat, short)
        if not r.get("ok") or int(r.get("filled", 0)) < short:
            return False
    return _can_afford_road_build(world, party)


def pick_road_edge(world: World, plot_id: PlotId) -> tuple[PlotId, PlotId] | None:
    """Best unbuilt adjacent edge to attach ``plot_id`` to the road network."""
    if is_road_accessible(world, plot_id):
        return None
    scored: list[tuple[int, PlotId]] = []
    for adj in _adjacent_plot_ids(world, plot_id):
        if find_segment_between(world, plot_id, adj) is not None:
            continue
        if is_road_accessible(world, adj):
            scored.append((10_000, adj))
            continue
        steps = _bfs_steps_to_road_network(world, adj)
        if steps >= 0:
            scored.append((5_000 - steps, adj))
        else:
            scored.append((1, adj))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], str(t[1])))
    return (plot_id, scored[0][1])


def try_connect_plot_with_road(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    buy_material: BuyFn | None = None,
) -> bool:
    if not plot_needs_road_access(world, party, plot_id):
        return False
    if not ensure_road_build_supplies(world, party, buy_material=buy_material):
        return False
    edge = pick_road_edge(world, plot_id)
    if edge is None:
        return False
    a, b = edge
    r = build_road(world, party, a, b)
    if not r.get("ok"):
        return False
    log_event(
        world,
        "npc_self_road",
        f"{party} built {r.get('segment_id')} for road access to {plot_id}",
        party=str(party),
        plot_id=str(plot_id),
        segment_id=str(r.get("segment_id", "")),
    )
    return True


def _plots_needing_roads(world: World, party: PartyId) -> list[PlotId]:
    out: list[PlotId] = []
    seen: set[str] = set()
    for row in world.plot_buildings:
        if str(row.get("party", "")) != str(party):
            continue
        pid_s = str(row.get("plot_id", ""))
        if pid_s == "" or pid_s in seen:
            continue
        seen.add(pid_s)
        pid = PlotId(pid_s)
        if plot_needs_road_access(world, party, pid):
            out.append(pid)
    return out


def _daily_build_budget(world: World, party: PartyId) -> int:
    gst = world.scenario_state.setdefault("npc_self_roads", {})
    day = _game_day(world)
    key = str(party)
    row = gst.get(key)
    if isinstance(row, dict) and int(row.get("day", -1)) == day:
        used = int(row.get("built", 0))
        return max(0, _MAX_BUILDS_PER_PARTY_PER_DAY - used)
    return _MAX_BUILDS_PER_PARTY_PER_DAY


def _record_daily_build(world: World, party: PartyId) -> None:
    gst = world.scenario_state.setdefault("npc_self_roads", {})
    day = _game_day(world)
    key = str(party)
    row = gst.get(key)
    if not isinstance(row, dict) or int(row.get("day", -1)) != day:
        gst[key] = {"day": day, "built": 1}
    else:
        row["built"] = int(row.get("built", 0)) + 1


def tick_npc_self_roads(world: World) -> None:
    """Daily: NPCs connect workshops before (and after) the road-access grace deadline."""
    if world.scenario_id != "genesis":
        return
    prep_start = ROAD_REQUIREMENT_GRACE_TICKS - ROAD_PREP_LEAD_TICKS
    if int(world.tick) < prep_start:
        return
    if int(world.tick) % int(TICKS_PER_GAME_DAY) != 0:
        return
    from realm.economy.markets import market_buy

    urgent = int(world.tick) >= ROAD_REQUIREMENT_GRACE_TICKS
    for party in sorted(world.parties, key=str):
        if _party_skipped(party):
            continue
        budget = _daily_build_budget(world, party)
        if urgent:
            budget = max(budget, _MAX_BUILDS_PER_PARTY_PER_DAY)
        if budget <= 0:
            continue
        for plot_id in _plots_needing_roads(world, party):
            if budget <= 0:
                break
            if try_connect_plot_with_road(
                world,
                party,
                plot_id,
                buy_material=market_buy,
            ):
                _record_daily_build(world, party)
                budget -= 1


def try_party_self_roads(
    world: World,
    party: PartyId,
    plot_ids: tuple[PlotId, ...] | list[PlotId],
    *,
    buy_material: BuyFn | None = None,
    max_attempts: int = 1,
) -> bool:
    """Per-tick hook (settler burst): try up to ``max_attempts`` segments."""
    if _party_skipped(party):
        return False
    attempts = 0
    for plot_id in plot_ids:
        if attempts >= max_attempts:
            break
        if try_connect_plot_with_road(world, party, plot_id, buy_material=buy_material):
            attempts += 1
            return True
    return False

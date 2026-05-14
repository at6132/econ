"""Frontier Roads Co. — NPC road builder (Sprint 6 — Phase A.4).

Builds road segments along the highest-traffic region pairs at a steady cadence
of 1–2 segments per game-day, sets a default toll of 3%, and avoids stepping on
plots reserved for tests or player-first claims.

Deterministic algorithm:
  * pick the highest-shipment route pair from
    ``world.scenario_state["route_shipment_counts"]`` (per-region-pair tally
    maintained by ``route_operators``);
  * walk the deterministic Manhattan path between the two region centres;
  * find the first edge with no existing road segment and build it.

The party is pre-funded at bootstrap; building costs come from that wallet.
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.geo import manhattan
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account, system_reserve_account
from realm.regions import all_region_ids, region_centre_coords, region_for_plot, route_key
from realm.roads import (
    BUILD_COST_CENTS,
    BUILD_MATERIALS,
    build_road,
    find_segment_between,
    set_road_toll,
)
from realm.time_scale import TICKS_PER_GAME_DAY
from realm.world import World

FRONTIER_ROADS_PARTY_ID: PartyId = PartyId("frontier_roads")
FRONTIER_ROADS_DISPLAY_NAME: str = "Frontier Roads Co."
FRONTIER_ROADS_STARTING_CASH_CENTS: int = 8_000_000  # $80,000

DEFAULT_TOLL_PCT: int = 3
MAX_BUILDS_PER_GAME_DAY: int = 3


# ────────────────────────────────────────────────────────────────────────
# Seed
# ────────────────────────────────────────────────────────────────────────


def seed_frontier_roads(world: World) -> None:
    """Seed the Frontier Roads Co. party with a starting wallet and materials."""
    if FRONTIER_ROADS_PARTY_ID in world.parties:
        return
    world.parties.add(FRONTIER_ROADS_PARTY_ID)
    world.party_display_names[str(FRONTIER_ROADS_PARTY_ID)] = FRONTIER_ROADS_DISPLAY_NAME
    world.reputation[str(FRONTIER_ROADS_PARTY_ID)] = {"honored": 0, "breached": 0}
    cash = party_cash_account(FRONTIER_ROADS_PARTY_ID)
    world.ledger.ensure_account(cash)
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=cash,
        amount_cents=FRONTIER_ROADS_STARTING_CASH_CENTS,
    )
    # Bootstrap materials: stockpile enough for ~30 builds (lumber 60, stone 60).
    world.inventory.add(FRONTIER_ROADS_PARTY_ID, MaterialId("lumber"), 200)
    world.inventory.add(FRONTIER_ROADS_PARTY_ID, MaterialId("stone"), 200)


# ────────────────────────────────────────────────────────────────────────
# Daily tick — pick edges and build
# ────────────────────────────────────────────────────────────────────────


def _route_shipment_count_map(world: World) -> dict[str, int]:
    """Return ``route_key -> shipments today`` (defaults to empty)."""
    raw = world.scenario_state.get("route_shipment_counts") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def _ordered_target_routes(world: World) -> list[tuple[str, str]]:
    """All region pairs ordered by descending shipment volume, ties by canonical key.

    Falls back to a deterministic enumeration of every region pair when no
    traffic has been recorded yet (early game).
    """
    counts = _route_shipment_count_map(world)
    regions = all_region_ids()
    pairs: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for a in regions:
        for b in regions:
            if a == b:
                continue
            k = route_key(a, b)
            if k in seen:
                continue
            seen.add(k)
            pairs.append((a, b, counts.get(k, 0)))
    pairs.sort(key=lambda t: (-t[2], route_key(t[0], t[1])))
    return [(a, b) for a, b, _ in pairs]


def _world_bounds(world: World) -> tuple[int, int]:
    if not world.plots:
        return (1, 1)
    mx, my = 0, 0
    for p in world.plots.values():
        if p.x > mx:
            mx = p.x
        if p.y > my:
            my = p.y
    return (mx + 1, my + 1)


def _plot_id_for_coords(world: World, x: int, y: int) -> PlotId | None:
    for pid, plot in world.plots.items():
        if plot.x == x and plot.y == y:
            return pid
    return None


def _candidate_edge_for_route(
    world: World, region_a: str, region_b: str
) -> tuple[PlotId, PlotId] | None:
    """Walk a deterministic Manhattan path between the region centres and
    return the first adjacent-plot edge that has no road yet."""
    w, h = _world_bounds(world)
    ax, ay = region_centre_coords(region_a, w, h)
    bx, by = region_centre_coords(region_b, w, h)
    cx, cy = ax, ay
    dx = 1 if bx > ax else (-1 if bx < ax else 0)
    dy = 1 if by > ay else (-1 if by < ay else 0)
    while cx != bx:
        nxt = (cx + dx, cy)
        a_pid = _plot_id_for_coords(world, cx, cy)
        b_pid = _plot_id_for_coords(world, *nxt)
        if a_pid is None or b_pid is None:
            return None
        if find_segment_between(world, a_pid, b_pid) is None:
            return (a_pid, b_pid)
        cx = nxt[0]
    while cy != by:
        nxt = (cx, cy + dy)
        a_pid = _plot_id_for_coords(world, cx, cy)
        b_pid = _plot_id_for_coords(world, *nxt)
        if a_pid is None or b_pid is None:
            return None
        if find_segment_between(world, a_pid, b_pid) is None:
            return (a_pid, b_pid)
        cy = nxt[1]
    return None


def _has_materials_and_cash(world: World) -> bool:
    if world.ledger.balance(party_cash_account(FRONTIER_ROADS_PARTY_ID)) < BUILD_COST_CENTS:
        return False
    for mat, need in BUILD_MATERIALS.items():
        if world.inventory.qty(FRONTIER_ROADS_PARTY_ID, mat) < need:
            return False
    return True


def tick_frontier_roads(world: World) -> None:
    """Once per game-day: build up to ``MAX_BUILDS_PER_GAME_DAY`` segments."""
    if FRONTIER_ROADS_PARTY_ID not in world.parties:
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % int(TICKS_PER_GAME_DAY) != 0:
        return
    built_today = 0
    for region_a, region_b in _ordered_target_routes(world):
        if built_today >= MAX_BUILDS_PER_GAME_DAY:
            break
        if not _has_materials_and_cash(world):
            break
        edge = _candidate_edge_for_route(world, region_a, region_b)
        if edge is None:
            continue
        r = build_road(world, FRONTIER_ROADS_PARTY_ID, edge[0], edge[1])
        if not r.get("ok"):
            continue
        set_road_toll(
            world, FRONTIER_ROADS_PARTY_ID, str(r["segment_id"]), DEFAULT_TOLL_PCT
        )
        built_today += 1
        log_event(
            world,
            "frontier_roads_built",
            f"Frontier Roads Co. built {r['segment_id']} between {edge[0]} and {edge[1]} (toll {DEFAULT_TOLL_PCT}%)",
            party=str(FRONTIER_ROADS_PARTY_ID),
            segment_id=str(r["segment_id"]),
            from_plot=str(edge[0]),
            to_plot=str(edge[1]),
        )

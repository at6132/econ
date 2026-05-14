"""NPC shipping companies — Tier-2 agents that operate inter-region routes.

Sprint 2 — Phase A.

At genesis bootstrap we seed 3 named NPC shippers. Each:
- claims a coastal plot in a distinct region,
- gets a completed ``dock`` (no construction lag),
- holds 1 ``vessel`` in inventory,
- auto-registers as the operator for every route touching their home region
  at ``NPC_SHIPPER_BASELINE_FEE_PER_TILE_CENTS`` (= 3¢/tile).

Every game-day, each NPC shipper consults its previous-day fee revenue. If
revenue is healthy (≥ threshold) they hold. If they are being undercut, they
shave 1¢ off their fee on the worst-performing route, fighting toward a 1¢
floor. At the floor they sit and wait — an exiting NPC opens room for a
single player operator to keep the route lit.

The NPC AI is intentionally simple and deterministic. There are no special
event hooks; from the player's perspective they are just another seller.
"""

from __future__ import annotations

from typing import Final

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world.regions import (
    REGION_GRID_DIM,
    all_region_ids,
    region_for_coords,
    region_for_plot,
    route_key,
)
from realm.route_operators import (
    ensure_route_state_initialised,
    list_route_operators,
    register_route,
    route_revenue_by_party_previous_day,
    set_operator_fee,
)
from realm.recipe_sites import plot_is_coastal
from realm.world import World


NPC_SHIPPER_IDS: Final[tuple[PartyId, ...]] = (
    PartyId("shipper_north_coast"),
    PartyId("shipper_south_coast"),
    PartyId("shipper_east_coast"),
)
NPC_SHIPPER_DISPLAY_NAMES: Final[dict[str, str]] = {
    "shipper_north_coast": "Northwind Coastal Lines",
    "shipper_south_coast": "Southreach Maritime",
    "shipper_east_coast": "Eastlight Shipping Co.",
}

NPC_SHIPPER_STARTING_CASH_CENTS: Final[int] = 200_000  # $2,000
NPC_SHIPPER_BASELINE_FEE_PER_TILE_CENTS: Final[int] = 3
NPC_SHIPPER_FEE_FLOOR_CENTS: Final[int] = 1
NPC_SHIPPER_HEALTHY_DAILY_REVENUE_CENTS: Final[int] = 500  # $5/day per spec

_TICKS_PER_GAME_DAY: Final[int] = 1440


# ────────────────────────── bootstrap ──────────────────────────


def _pick_coastal_plot_in_region(
    world: World, region_id: str, exclude_plots: set[str]
) -> PlotId | None:
    """First unowned coastal plot in ``region_id`` not in ``exclude_plots``."""
    from realm.world.regions import _world_bounds

    w, h = _world_bounds(world)
    candidates: list[tuple[int, int, PlotId]] = []
    for plot in world.plots.values():
        if plot.owner is not None:
            continue
        if str(plot.plot_id) in exclude_plots:
            continue
        if region_for_coords(plot.x, plot.y, w, h) != region_id:
            continue
        if not plot_is_coastal(world, plot):
            continue
        candidates.append((plot.x, plot.y, plot.plot_id))
    if not candidates:
        return None
    # Deterministic pick: closest to the region centre, then lex-smallest id.
    from realm.world.regions import region_centre_coords

    cx, cy = region_centre_coords(region_id, w, h)
    candidates.sort(key=lambda t: (abs(t[0] - cx) + abs(t[1] - cy), str(t[2])))
    return candidates[0][2]


def _coastal_regions(world: World) -> list[str]:
    """Region ids that contain at least one coastal plot (deterministic order)."""
    from realm.world.regions import _world_bounds

    w, h = _world_bounds(world)
    counts: dict[str, int] = {r: 0 for r in all_region_ids()}
    for plot in world.plots.values():
        if not plot_is_coastal(world, plot):
            continue
        r = region_for_coords(plot.x, plot.y, w, h)
        counts[r] = counts.get(r, 0) + 1
    return [r for r, c in counts.items() if c > 0]


def seed_npc_shippers(world: World, *, starting_cash_cents: int | None = None) -> list[str]:
    """Spawn the 3 NPC shippers if they don't already exist.

    Returns the list of party ids that were created (empty if shippers were
    already present from a previous snapshot). Idempotent.
    """
    if world.scenario_id != "genesis":
        return []
    created: list[str] = []
    cash_cents = (
        starting_cash_cents
        if starting_cash_cents is not None
        else NPC_SHIPPER_STARTING_CASH_CENTS
    )

    coastal_regions = _coastal_regions(world)
    if not coastal_regions:
        return []
    # Stable, deterministic mapping of shipper → region.
    chosen_regions = coastal_regions[: len(NPC_SHIPPER_IDS)]
    # If we have fewer coastal regions than shippers, deduplicate by wrapping; in practice
    # the standard 96×72 map has all 9 regions but only the border-region group is coastal.
    while len(chosen_regions) < len(NPC_SHIPPER_IDS):
        chosen_regions.append(coastal_regions[len(chosen_regions) % len(coastal_regions)])

    excluded: set[str] = set()
    for shipper_id, region in zip(NPC_SHIPPER_IDS, chosen_regions):
        if shipper_id in world.parties:
            continue  # already seeded
        plot_id = _pick_coastal_plot_in_region(world, region, excluded)
        if plot_id is None:
            # No coastal plot anywhere in this region — skip this shipper rather than
            # crash bootstrap (degraded mode for tiny test worlds).
            continue
        excluded.add(str(plot_id))
        plot = world.plots[plot_id]
        world.parties.add(shipper_id)
        world.reputation[str(shipper_id)] = {"honored": 0, "breached": 0}
        acct = party_cash_account(shipper_id)
        world.ledger.ensure_account(acct)
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=cash_cents,
        )
        if isinstance(tr, MoneyErr):
            continue
        plot.owner = shipper_id
        # Seed a completed dock — bypass the build pipeline so it's ready at t=0.
        world.next_building_instance_seq += 1
        instance_id = f"b{world.next_building_instance_seq:06d}"
        world.plot_buildings.append(
            {
                "instance_id": instance_id,
                "condition_bps": 10_000,
                "plot_id": str(plot_id),
                "party": str(shipper_id),
                "building_id": "dock",
                "label": "Coastal dock (NPC shipper)",
                "cost_cents": 0,
                "build_mode": "turnkey",
                "completes_at_tick": 0,
            }
        )
        world.building_maintenance[instance_id] = {
            "due_at_tick": int(world.tick) + 7_200,
            "missed_cycles": 0,
            "efficiency_pct": 100,
        }
        # Give the shipper one vessel (durable; the route-registration precondition).
        ad = world.inventory.add(shipper_id, MaterialId("vessel"), 1)
        if isinstance(ad, MatterErr):
            continue
        created.append(str(shipper_id))
        log_event(
            world,
            "npc_shipper_seeded",
            f"NPC shipper {shipper_id} placed on {plot_id} (region {region}) with dock + 1 vessel",
            party=str(shipper_id),
            plot_id=str(plot_id),
            region=region,
        )
        # Register operator for every route touching this shipper's home region.
        for other in all_region_ids():
            if other == region:
                continue
            register_route(
                world,
                shipper_id,
                plot_id,
                region,
                other,
                NPC_SHIPPER_BASELINE_FEE_PER_TILE_CENTS,
            )
    ensure_route_state_initialised(world)
    return created


# ────────────────────────── daily action loop ──────────────────────────


def _shipper_home_region(world: World, party: PartyId) -> str | None:
    """The region of the NPC shipper's owned dock plot (None if no dock plot)."""
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) != "dock":
            continue
        return region_for_plot(world, PlotId(str(row["plot_id"])))
    return None


def _shipper_home_plot(world: World, party: PartyId) -> PlotId | None:
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) != "dock":
            continue
        return PlotId(str(row["plot_id"]))
    return None


def _routes_operated_by(world: World, party: PartyId) -> list[tuple[str, dict]]:
    """All ``(route_key, entry)`` pairs where ``party`` is a registered operator."""
    operators = world.scenario_state.get("route_operators") or {}
    out: list[tuple[str, dict]] = []
    for key, entries in operators.items():
        for e in entries:
            if str(e.get("operator_party")) == str(party):
                out.append((str(key), e))
                break
    return out


def tick_npc_shippers(world: World) -> None:
    """Once per game-day, advance the NPC shipping AI.

    Runs **before** ``tick_population_demands`` so any fee revisions are in
    effect before the next round of shipments. No-op on non-genesis worlds and
    on ticks that aren't a day boundary.
    """
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    for shipper in NPC_SHIPPER_IDS:
        if shipper not in world.parties:
            continue
        revenue = route_revenue_by_party_previous_day(world, shipper)
        if revenue >= NPC_SHIPPER_HEALTHY_DAILY_REVENUE_CENTS:
            continue
        my_routes = _routes_operated_by(world, shipper)
        if not my_routes:
            # No registrations — try to re-register on home routes.
            home = _shipper_home_region(world, shipper)
            home_plot = _shipper_home_plot(world, shipper)
            if home is None or home_plot is None:
                continue
            for other in all_region_ids():
                if other == home:
                    continue
                register_route(
                    world,
                    shipper,
                    home_plot,
                    home,
                    other,
                    NPC_SHIPPER_BASELINE_FEE_PER_TILE_CENTS,
                )
            continue
        # Find the route most in need of price action: lowest competitor fee that's
        # below this NPC's. Drop our fee on that route by 1¢, with the floor at 1¢.
        adjusted_any = False
        for key, my_entry in my_routes:
            my_fee = int(my_entry.get("fee_per_tile_cents", 0))
            entries = list_route_operators(world, key)
            cheapest = entries[0] if entries else None
            if cheapest is None:
                continue
            if str(cheapest.get("operator_party")) == str(shipper):
                continue  # we're already cheapest on this route
            comp_fee = int(cheapest.get("fee_per_tile_cents", my_fee))
            new_fee = max(NPC_SHIPPER_FEE_FLOOR_CENTS, comp_fee - 1)
            if new_fee >= my_fee:
                continue
            set_operator_fee(world, shipper, key, new_fee)
            adjusted_any = True
            log_event(
                world,
                "npc_shipper_undercut",
                f"{shipper} cut {key} to {new_fee}¢/tile to undercut {comp_fee}¢ competitor",
                party=str(shipper),
                route_key=key,
                fee_per_tile_cents=new_fee,
            )
        # If we are already at the floor on every route and still unprofitable, expand
        # into a route we don't currently operate.
        if not adjusted_any:
            at_floor = all(
                int(e.get("fee_per_tile_cents", 0)) <= NPC_SHIPPER_FEE_FLOOR_CENTS
                for _, e in my_routes
            )
            if not at_floor:
                continue
            home = _shipper_home_region(world, shipper)
            home_plot = _shipper_home_plot(world, shipper)
            if home is None or home_plot is None:
                continue
            owned_keys = {k for k, _ in my_routes}
            for other in all_region_ids():
                if other == home:
                    continue
                key = route_key(home, other)
                if key in owned_keys:
                    continue
                register_route(
                    world,
                    shipper,
                    home_plot,
                    home,
                    other,
                    NPC_SHIPPER_BASELINE_FEE_PER_TILE_CENTS,
                )
                break  # one new route per day

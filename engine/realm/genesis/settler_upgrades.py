"""Settler vertical integration — weekly margin-analysis upgrade triggers.

Sprint 2 — Phase B.

Once per game-week, each settler reviews the margin they're earning on their
primary line vs. the margin they'd earn one production step further down the
chain (vertical integration). When the downstream margin is sufficiently
better and the settler has the cash buffer, they kick off a turnkey build of
the upgrade workshop.

Upgrade paths (extract → process):
    strip_mine + iron_ore     → foundry      → iron_ingot (smelt_iron)
    strip_mine + coal         → power_shed   → electricity (coal_generator)
    timber_yard               → wood_shop    → lumber     (sawmill)
    grain_row                 → gristmill    → flour      (mill_flour)

Triggers when ``vertical_margin > current_margin * 2.5`` and
``cash >= turnkey_total_cents * 1.5``. No special-case scripting — if the
margin math doesn't fire, the upgrade doesn't fire (per Sprint 2 design rule).

Buffer buying (Phase B.4): when a settler's input price for ``material`` has
risen by ``SETTLER_BUFFER_BUY_PRICE_RISE_BPS`` (20%) over the last 7 days
*and* they have an active workshop that consumes that material, they buy
``SETTLER_BUFFER_BUY_DAYS_FORWARD`` (3) game-days of forward consumption in
a single sweep.
"""

from __future__ import annotations

from typing import Any

from realm.production.buildings import BUILDINGS, build_on_plot
from realm.events.event_log import log_event
from realm.economy.pricing import exchange_ask_cents
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.economy.markets import market_buy
from realm.production.recipes import RECIPES
from realm.genesis.settler_cost_basis import (
    SETTLER_BUFFER_BUY_DAYS_FORWARD,
    SETTLER_BUFFER_BUY_PRICE_RISE_BPS,
    record_settler_buy,
    settler_input_avg_paid_cents,
    settler_input_price_change_bps_7d,
    settler_output_basis_cents,
)
from realm.world import World


__all__ = [
    "tick_settler_margin_review",
    "VERTICAL_TRIGGER_RATIO_BPS",
    "VERTICAL_CASH_BUFFER_BPS",
    "ROAD_BUILD_CASH_THRESHOLD",
    "JOB_POSTING_CASH_THRESHOLD",
    "JOB_WAGE_CENTS_PER_DAY",
    "_maybe_post_job_openings",
    "_maybe_build_settler_road",
    "_maybe_build_power_shed",
]


VERTICAL_TRIGGER_RATIO_BPS: int = 25_000  # vertical must beat current by 2.5×
VERTICAL_CASH_BUFFER_BPS: int = 15_000  # cash ≥ turnkey × 1.5

_TICKS_PER_GAME_DAY: int = 1440
_REVIEW_INTERVAL_TICKS: int = 7 * _TICKS_PER_GAME_DAY
_TICKS_PER_GAME_WEEK: int = 7 * _TICKS_PER_GAME_DAY
_TICKS_PER_GAME_MONTH: int = 30 * _TICKS_PER_GAME_DAY

ROAD_BUILD_CASH_THRESHOLD: int = 300_000
ROAD_BUILD_MATERIALS_PER_SEGMENT: dict[str, int] = {
    "lumber": 2,
    "stone": 2,
}
_MAX_ROAD_SEGMENTS_PER_WEEK: int = 3
_POWER_SHED_CASH_THRESHOLD: int = 500_000

JOB_POSTING_CASH_THRESHOLD: int = 100_000
JOB_WAGE_CENTS_PER_DAY: int = 800


# (upstream_building, upstream_material, downstream_building, downstream_recipe,
#  downstream_output)
_UPGRADE_PATHS: list[tuple[str, str, str, str, str]] = [
    ("strip_mine", "iron_ore", "foundry", "smelt_iron", "iron_ingot"),
    ("strip_mine", "coal", "power_shed", "coal_generator", "electricity"),
    ("timber_yard", "timber", "wood_shop", "sawmill", "lumber"),
    ("grain_row", "grain", "gristmill", "mill_flour", "flour"),
]


# ───────────────────────── helpers ─────────────────────────


def _party_owns_building(world: World, party: PartyId, building_id: str) -> bool:
    target = str(building_id)
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) == target:
            return True
    return False


def _party_owns_plot_for_building(
    world: World, party: PartyId, building_id: str
) -> PlotId | None:
    """A plot owned by ``party`` that already has ``building_id`` on it (for upgrade siting)."""
    target = str(building_id)
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) == target:
            return PlotId(str(row.get("plot_id")))
    return None


def _market_unit_price(world: World, material: MaterialId) -> int:
    """Best deterministic estimate of what 1 unit of ``material`` clears at right now."""
    return int(exchange_ask_cents(material, world=world))


def _recipe_per_unit_input_cost(
    world: World, party: PartyId, recipe_id: str, output_material: MaterialId
) -> tuple[int, int] | None:
    """Per-unit input cost & per-unit labor for ``recipe_id`` producing ``output_material``.

    Inputs the settler is currently buying use ``settler_input_avg_paid``; if no
    history exists, fall back to the current exchange ask. Returns
    ``(input_cents_per_output_unit, labor_cents_per_output_unit)`` or ``None``
    if the recipe doesn't actually produce ``output_material``.
    """
    rec = RECIPES.get(recipe_id)
    if rec is None:
        return None
    out_qty = int(rec.outputs.get(output_material, 0))
    if out_qty <= 0:
        return None
    in_cents = 0
    for inp, in_qty in rec.inputs.items():
        unit = settler_input_avg_paid_cents(world, party, inp)
        if unit is None:
            unit = _market_unit_price(world, inp)
        in_cents += int(unit) * int(in_qty)
    labor_per_unit = (int(getattr(rec, "labor_cents", 0)) + out_qty - 1) // out_qty
    return ((in_cents + out_qty - 1) // out_qty, labor_per_unit)


# ───────────────────────── core review pass ─────────────────────────


def _maybe_trigger_upgrade(
    world: World, party: PartyId, path: tuple[str, str, str, str, str]
) -> bool:
    """Evaluate one upgrade path; build the downstream workshop if the math justifies it.

    Returns True if a build was kicked off this call (caller can stop further
    upgrade attempts this week — one big capex per week is plenty).
    """
    upstream_b, upstream_mat, downstream_b, downstream_recipe, downstream_out = path

    src_plot = _party_owns_plot_for_building(world, party, upstream_b)
    if src_plot is None:
        return False
    if _party_owns_building(world, party, downstream_b):
        return False  # already vertically integrated for this path

    upstream_mid = MaterialId(upstream_mat)
    downstream_mid = MaterialId(downstream_out)

    # ── current margin: settler sells upstream_mat at market.
    upstream_price = _market_unit_price(world, upstream_mid)
    upstream_basis = settler_output_basis_cents(world, party, upstream_mid)
    # A settler with no production history for the upstream input is treated as a
    # zero-cost producer (they'll start extracting once the workshop is online).
    if upstream_basis is None:
        upstream_basis = 0
    current_margin = max(0, upstream_price - upstream_basis)

    # ── vertical margin: settler keeps upstream_mat as zero-cost input, smelts/processes,
    #    sells downstream_mat at market. Use the *recipe* cost ignoring upstream input cost
    #    (because they would extract it themselves).
    rec = RECIPES.get(downstream_recipe)
    if rec is None:
        return False
    downstream_price = _market_unit_price(world, downstream_mid)
    rec_out_qty = int(rec.outputs.get(downstream_mid, 0))
    if rec_out_qty <= 0:
        return False
    other_input_cents = 0
    for inp, in_qty in rec.inputs.items():
        if str(inp) == upstream_mat:
            continue  # would be free (self-supplied)
        unit = settler_input_avg_paid_cents(world, party, inp)
        if unit is None:
            unit = _market_unit_price(world, inp)
        other_input_cents += int(unit) * int(in_qty)
    labor_cents = int(getattr(rec, "labor_cents", 0))
    vertical_cost_per_out = (other_input_cents + labor_cents + rec_out_qty - 1) // rec_out_qty
    vertical_margin = max(0, downstream_price - vertical_cost_per_out)

    # ── decision gate.
    trigger = current_margin * VERTICAL_TRIGGER_RATIO_BPS // 10_000
    if vertical_margin <= max(1, trigger):
        return False
    spec = BUILDINGS.get(downstream_b) or {}
    turnkey = int(spec.get("turnkey_total_cents", 0))
    if turnkey <= 0:
        return False
    cash = int(world.ledger.balance(party_cash_account(party)))
    if cash * 10_000 < turnkey * VERTICAL_CASH_BUFFER_BPS:
        return False

    # ── attempt the build. We piggyback on the standard turnkey path: buy any
    # missing self_materials, then build_on_plot. ``_settler_acquire_turnkey_materials``
    # is private to the settler module — recreate it here to avoid a circular import.
    mats = spec.get("self_materials") or {}
    for mid_s, qty in mats.items():
        mid = MaterialId(mid_s)
        need = int(qty) - int(world.inventory.qty(party, mid))
        if need <= 0:
            continue
        r = market_buy(world, party, mid, need)
        if r.get("ok"):
            record_settler_buy(
                world,
                party,
                mid,
                int(r.get("filled", 0)),
                int(r.get("spent_cents", 0)),
            )
        if not r.get("ok") or int(r.get("filled", 0)) < need:
            return False  # insufficient market depth; try again next week
    built = build_on_plot(world, party, src_plot, downstream_b, build_mode="turnkey")
    if not built.get("ok"):
        return False
    log_event(
        world,
        "settler_vertical_upgrade",
        f"{party} initiated vertical upgrade {upstream_b}→{downstream_b} on {src_plot}",
        party=str(party),
        plot_id=str(src_plot),
        upstream_building=upstream_b,
        downstream_building=downstream_b,
        current_margin_cents=int(current_margin),
        vertical_margin_cents=int(vertical_margin),
    )
    return True


def _maybe_buffer_buy(world: World, party: PartyId) -> None:
    """Phase B.4 — when an input price rose ≥ 20% in 7 days, prebuy 3 days' worth.

    Only triggers for materials the settler is *already* buying from the market
    (so we have price history) **and** consumes via an active workshop. We
    estimate forward consumption from the recipe currently running (if any)
    or, as a default, from the recipe inputs of the upstream-paths above.
    """
    root = world.scenario_state.get("settler_cost_basis") or {}
    blob = root.get(str(party)) or {}
    avg_map = blob.get("input_avg_paid") or {}
    if not avg_map:
        return
    for mid_s in list(avg_map.keys()):
        change_bps = settler_input_price_change_bps_7d(world, party, MaterialId(mid_s))
        if change_bps is None:
            continue
        if int(change_bps) < SETTLER_BUFFER_BUY_PRICE_RISE_BPS:
            continue
        # Conservative forward-consumption estimate: 6 units per game-day (covers a
        # single workshop running once per ~4 hours).
        per_day = 6
        for run in world.active_production:
            if str(run.party) != str(party):
                continue
            rec = RECIPES.get(run.recipe_id)
            if rec is None:
                continue
            qty = int(rec.inputs.get(MaterialId(mid_s), 0))
            if qty <= 0:
                continue
            per_day = max(per_day, qty * 6)
            break
        target_qty = per_day * SETTLER_BUFFER_BUY_DAYS_FORWARD
        have = int(world.inventory.qty(party, MaterialId(mid_s)))
        deficit = target_qty - have
        if deficit <= 0:
            continue
        r = market_buy(world, party, MaterialId(mid_s), deficit)
        if r.get("ok"):
            record_settler_buy(
                world,
                party,
                MaterialId(mid_s),
                int(r.get("filled", 0)),
                int(r.get("spent_cents", 0)),
            )
            if int(r.get("filled", 0)) > 0:
                log_event(
                    world,
                    "settler_buffer_buy",
                    f"{party} buffered {r['filled']}×{mid_s} (price up {change_bps}bps in 7d)",
                    party=str(party),
                    material=str(mid_s),
                    filled=int(r.get("filled", 0)),
                    spent_cents=int(r.get("spent_cents", 0)),
                    price_change_bps_7d=int(change_bps),
                )


_STALE_ORDER_DAYS = 3
_PRICE_DOWN_PCT = 0.08


def _plot_archetype_score(
    world: World, pid: PlotId, plot: object, archetype: object
) -> float:
    from realm.agents.settler_archetypes import Archetype
    from realm.world.real_estate import _min_town_distance

    score = 0.0
    terrain = str(getattr(plot, "terrain", "")).lower()

    if archetype == Archetype.MINER:
        if "mountain" in terrain or "hill" in terrain:
            score += 3.0
        sub = getattr(plot, "subsurface", None)
        if sub is not None:
            for attr in ("iron_ore_grade", "coal_grade", "copper_ore_grade"):
                score += float(getattr(sub, attr, 0.0)) * 5.0

    elif archetype == Archetype.PROCESSOR:
        if "plain" in terrain or "valley" in terrain:
            score += 2.0

    elif archetype == Archetype.MERCHANT:
        dist = _min_town_distance(world, plot)
        score += max(0.0, 10.0 - dist)

    elif archetype == Archetype.LANDLORD:
        if "coastal" in terrain:
            score += 4.0
        score += max(0.0, 8.0 - _min_town_distance(world, plot))

    elif archetype == Archetype.RESEARCHER:
        sub = getattr(plot, "subsurface", None)
        if sub is not None:
            for attr in ("au_grade", "nd_grade", "platinum_ore_grade"):
                score += float(getattr(sub, attr, 0.0)) * 10.0

    return score


def _maybe_expand_capital(world: World, party: PartyId) -> bool:
    from realm.actions.plot_actions import claim_plot
    from realm.agents.market_oracle import get_oracle
    from realm.agents.settler_archetypes import (
        ARCHETYPE_EXPANSION_THRESHOLD,
        get_archetype,
    )
    from realm.world.real_estate import compute_plot_value

    archetype = get_archetype(party)
    threshold = ARCHETYPE_EXPANSION_THRESHOLD[archetype]
    cash = int(world.ledger.balance(party_cash_account(party)))
    if cash < threshold:
        return False

    owned = [pid for pid, p in world.plots.items() if p.owner == party]
    if len(owned) >= 2:
        return False

    get_oracle(world)
    candidates: list[tuple[float, PlotId]] = []
    for pid, plot in world.plots.items():
        if plot.owner is not None:
            continue
        terr = str(plot.terrain)
        if terr.startswith("water") or terr == "water_shallow":
            continue
        value = compute_plot_value(world, pid)
        if value > cash * 0.6:
            continue
        score = _plot_archetype_score(world, pid, plot, archetype)
        candidates.append((score, pid))

    if not candidates:
        return False

    candidates.sort(reverse=True)
    best_pid = candidates[0][1]
    r = claim_plot(world, party, best_pid)
    if r.get("ok"):
        log_event(
            world,
            "settler_expanded",
            f"{party} claimed 2nd plot {best_pid} (archetype: {archetype.value})",
            party=str(party),
        )
        return True
    return False


def _maybe_reprice_stale_orders(world: World, party: PartyId) -> None:
    from realm.agents.market_oracle import get_oracle
    from realm.economy.markets import cancel_party_asks_for_material, place_sell_order

    oracle = get_oracle(world)
    stale_tracker: dict[str, dict[str, object]] = world.scenario_state.setdefault(
        "settler_stale_orders", {}
    )
    party_key = str(party)

    ask_mats: dict[str, tuple[int, int]] = {}
    for mat, asks in world.market_asks_by_material.items():
        for ask in asks:
            if ask.party != party:
                continue
            mid = str(mat)
            if mid not in ask_mats:
                ask_mats[mid] = (int(ask.price_per_unit_cents), 0)
            old_price, old_qty = ask_mats[mid]
            ask_mats[mid] = (old_price, old_qty + int(ask.qty))

    for mid, (price, qty) in ask_mats.items():
        tracker_key = f"{party_key}:{mid}"
        tracker = dict(stale_tracker.get(tracker_key, {"days_listed": 0, "price": price}))
        tracker["days_listed"] = int(tracker.get("days_listed", 0)) + 1

        if int(tracker["days_listed"]) >= _STALE_ORDER_DAYS:
            new_price = int(price * (1 - _PRICE_DOWN_PCT))
            best_bid = int(oracle.best_bid.get(mid, 0))
            if new_price > best_bid * 0.9 and new_price >= 1 and qty > 0:
                mat = MaterialId(mid)
                cancelled = cancel_party_asks_for_material(world, party, mat)
                if cancelled > 0:
                    place_sell_order(world, party, mat, qty=qty, price_per_unit_cents=new_price)
                    tracker = {"days_listed": 0, "price": new_price}
                    log_event(
                        world,
                        "settler_repriced",
                        f"{party} lowered {mid} from {price}c to {new_price}c (stale)",
                        party=str(party),
                    )

        stale_tracker[tracker_key] = tracker


def _maybe_update_merchant_store_prices(world: World, party: PartyId) -> None:
    from realm.agents.market_oracle import get_oracle
    from realm.agents.settler_archetypes import Archetype, get_archetype

    if get_archetype(party) != Archetype.MERCHANT:
        return

    oracle = get_oracle(world)
    store_plots: set[str] = set()
    for b in world.plot_buildings:
        if str(b.get("party")) != str(party):
            continue
        if str(b.get("building_id")) != "store":
            continue
        if int(b.get("completes_at_tick", 0)) > int(world.tick):
            continue
        store_plots.add(str(b.get("plot_id", "")))

    for pid in store_plots:
        store_inv = world.store_inventories.get(pid, {})
        store_prices = world.store_prices.get(pid, {})
        if not store_prices:
            continue
        for mat_id, price in list(store_prices.items()):
            stock = int(store_inv.get(mat_id, 0))
            best_ask = int(oracle.best_ask.get(str(mat_id), price))
            if stock == 0:
                store_prices[mat_id] = min(int(price * 1.05), int(best_ask * 1.1))
            elif stock > 50:
                new_price = max(int(price * 0.92), int(best_ask * 0.85))
                store_prices[mat_id] = max(1, new_price)


def _maybe_subdivide_and_lease(world: World, party: PartyId) -> bool:
    from realm.actions.plot_actions import subdivide_plot
    from realm.agents.settler_archetypes import Archetype, get_archetype
    from realm.world.real_estate import compute_plot_value

    if get_archetype(party) != Archetype.LANDLORD:
        return False

    cash = int(world.ledger.balance(party_cash_account(party)))
    if cash < 500_000:
        return False

    owned = [pid for pid, p in world.plots.items() if p.owner == party]
    unbuilt = [
        pid
        for pid in owned
        if not world.plot_placed_buildings.get(str(pid))
        and not any(sp.parent_plot_id == str(pid) for sp in world.sub_plots.values())
    ]
    if not unbuilt:
        return False

    pid = unbuilt[0]
    partitions = [
        {"grid_x": 0, "grid_y": 0, "grid_w": 10, "grid_h": 5},
        {"grid_x": 0, "grid_y": 5, "grid_w": 10, "grid_h": 5},
    ]
    r = subdivide_plot(world, party, pid, partitions)
    if not r.get("ok"):
        return False

    listings = world.scenario_state.setdefault("sub_plot_listings", {})
    value = compute_plot_value(world, pid)
    rent = max(500, int(value * 0.02))
    for sp_id in r.get("sub_plot_ids", []):
        listings[str(sp_id)] = {
            "lessor": str(party),
            "rent_per_7days": rent,
            "available": True,
        }
    return True


def _maybe_post_job_openings(world: World, party: PartyId) -> int:
    from realm.population.employment import maybe_post_job_openings_for_party

    return maybe_post_job_openings_for_party(world, party)


def _maybe_build_settler_road(world: World, party: PartyId) -> bool:
    """Connect an isolated owned plot to the road network (up to 3 segments)."""
    from realm.infrastructure.road_connectivity import is_road_accessible
    from realm.infrastructure.npc_self_roads import (
        ensure_road_build_supplies,
        pick_road_edge,
    )
    from realm.infrastructure.roads import build_road

    if int(world.ledger.balance(party_cash_account(party))) < ROAD_BUILD_CASH_THRESHOLD:
        return False

    unconnected: list[PlotId] = []
    for pid, plot in world.plots.items():
        if plot.owner != party:
            continue
        if _is_water_plot(plot):
            continue
        if is_road_accessible(world, pid):
            continue
        unconnected.append(pid)
    if not unconnected:
        return False

    target = sorted(unconnected, key=str)[0]

    def _buy_material(w: World, p: PartyId, mat: MaterialId, qty: int) -> dict:
        return market_buy(w, p, mat, qty, max_price_per_unit_cents=500)

    if not ensure_road_build_supplies(world, party, buy_material=_buy_material):
        return False

    built = 0
    while built < _MAX_ROAD_SEGMENTS_PER_WEEK:
        if is_road_accessible(world, target):
            break
        edge = pick_road_edge(world, target)
        if edge is None:
            break
        result = build_road(world, party, edge[0], edge[1])
        if not result.get("ok"):
            break
        built += 1
        log_event(
            world,
            "settler_road_built",
            f"{party} built road {result.get('segment_id')} ({edge[0]} ↔ {edge[1]})",
            party=str(party),
            from_plot=str(edge[0]),
            to_plot=str(edge[1]),
            segment_id=str(result.get("segment_id", "")),
        )

    return built > 0


def _is_water_plot(plot: object) -> bool:
    terr = str(getattr(plot, "terrain", "")).lower()
    return terr.startswith("water") or terr == "water_shallow"


def _maybe_build_power_shed(world: World, party: PartyId) -> bool:
    """Place a power shed on a road-connected plot when the regional grid needs capacity."""
    from realm.actions.blueprint_actions import find_free_blueprint_position, place_blueprint
    from realm.infrastructure.power_grid import POWER_GENERATOR_BLUEPRINTS, compute_grid_regions
    from realm.infrastructure.road_connectivity import is_road_accessible

    if int(world.ledger.balance(party_cash_account(party))) < _POWER_SHED_CASH_THRESHOLD:
        return False

    for pb in world.placed_buildings.values():
        if str(pb.built_by) == str(party) and pb.blueprint_id == "power_shed":
            return False
    for row in world.plot_buildings:
        if str(row.get("party")) == str(party) and str(row.get("building_id")) == "power_shed":
            return False

    regions = compute_grid_regions(world)
    plot_to_region = {
        pid: reg for reg in regions.values() for pid in reg.plot_ids
    }

    for pid, plot in sorted(world.plots.items(), key=lambda t: str(t[0])):
        if plot.owner != party:
            continue
        if _is_water_plot(plot):
            continue
        if not is_road_accessible(world, pid):
            continue
        reg = plot_to_region.get(str(pid))
        if reg is None:
            continue
        needs_power = reg.load_factor > 0.6 or reg.capacity_per_day <= 0
        if not needs_power:
            continue
        pos = find_free_blueprint_position(world, pid, "power_shed")
        if pos is None:
            continue
        result = place_blueprint(
            world,
            party,
            pid,
            "power_shed",
            pos[0],
            pos[1],
            build_mode="turnkey",
        )
        if result.get("ok"):
            log_event(
                world,
                "settler_power_shed_built",
                f"{party} built power shed at {pid}",
                party=str(party),
                plot_id=str(pid),
                instance_id=str(result.get("instance_id", "")),
            )
            return True
    return False


def tick_settler_margin_review(world: World) -> None:
    """Once per game-week, evaluate every settler's vertical-integration triggers
    and run buffer-buy logic for materials whose price is rising fast.

    Called from ``tick_genesis_agents`` (after the per-tick settler business
    pipeline, before the population-demand sweep). A no-op on non-week-boundary
    ticks so it doesn't blow up runtime cost.
    """
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _REVIEW_INTERVAL_TICKS != 0:
        return
    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")), key=str
    )
    weekly = int(world.tick) % _TICKS_PER_GAME_WEEK == 0
    monthly = int(world.tick) % _TICKS_PER_GAME_MONTH == 0
    for party in settlers:
        # One upgrade per settler per week — the first path whose math fires wins.
        for path in _UPGRADE_PATHS:
            if _maybe_trigger_upgrade(world, party, path):
                break
        _maybe_buffer_buy(world, party)
        _maybe_expand_capital(world, party)
        _maybe_reprice_stale_orders(world, party)
        _maybe_update_merchant_store_prices(world, party)
        _maybe_subdivide_and_lease(world, party)
        _maybe_list_excess_electricity(world, party)
        _maybe_post_job_openings(world, party)
        if weekly:
            _maybe_build_settler_road(world, party)
        if monthly:
            _maybe_build_power_shed(world, party)


def _maybe_list_excess_electricity(world: World, party: PartyId) -> None:
    """Generators with excess electricity list it at the regional clearing price."""
    from realm.economy.markets import place_sell_order

    elec = world.inventory.qty(party, MaterialId("electricity"))
    if elec < 5:
        return

    regions = world.scenario_state.get("power_regions", [])
    ref_price = 40
    if regions:
        ref_price = max(int(r.get("clearing_price_cents", 40)) for r in regions)

    sell_qty = elec - 3
    if sell_qty >= 1:
        place_sell_order(
            world,
            party,
            MaterialId("electricity"),
            qty=sell_qty,
            price_per_unit_cents=ref_price,
        )

"""Goods in transit — Law 3 (time + distance).

Bulk shipping fee (integer cents): fixed **trip** cost amortized per unit.

``trip_cost = BASE_TRIP_FEE + distance * per_tile`` (per-tile may come from a
registered route operator). ``per_unit = max(MIN_PER_UNIT, trip_cost // qty)``;
``total_fee = per_unit * qty``.

Inter-island lanes apply ``OCEAN_TILE_MULTIPLIER``; uncharted lanes (no
operator) apply ``UNCHARTED_TRIP_MULTIPLIER``. Land movement across ocean
tiles is impassable (``tile_movement_cost == math.inf``).

Arrival tick uses Manhattan distance × ``TRANSIT_TICKS_PER_TILE`` (game-minutes
per tile) plus ``TRANSIT_BASE_TICKS`` handling.
"""

from __future__ import annotations

from typing import Final

from realm.events.event_log import log_event
from realm.world.geo import manhattan
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.infrastructure.plot_logistics import plot_output_qty, remove_plot_output, try_add_plot_output, uses_plot_logistics
from realm.world.regions import region_for_plot, route_key
from realm.infrastructure.route_operators import find_cheapest_operator, record_route_fee_collected
from realm.infrastructure.shipping_traffic import record_route_voyage_completed
from realm.production.storage_caps import try_add_inventory
from realm.core.time_scale import TRANSIT_BASE_TICKS, TRANSIT_TICKS_PER_TILE
from realm.world import InTransit, World

# Bulk-friendly trip pricing (Realism Pass 2).
BASE_TRIP_FEE_CENTS: Final[int] = 500
PER_TILE_TRIP_FEE_CENTS: Final[int] = 10
MIN_PER_UNIT_FEE_CENTS: Final[int] = 1
UNCHARTED_TRIP_MULTIPLIER: Final[float] = 2.0
OCEAN_TILE_MULTIPLIER: Final[float] = 1.5

# Backward-compat aliases for imports/tests that still reference old names.
PER_TILE_SHIP_CENTS = PER_TILE_TRIP_FEE_CENTS
BASE_SHIP_FEE_CENTS = BASE_TRIP_FEE_CENTS

# Sprint 3 — Phase D.2/D.3: coastal advantages.
COASTAL_ROUTE_DISCOUNT_BPS: int = 4_000  # 40 % discount → multiplier 0.60
HARBOR_TRANSIT_SPEEDUP_BPS: int = 5_000  # 50 % faster departure from dock plots

# Unloading / receiving (dock handling): paid when goods are accepted at destination; all parties alike.
RECEIVING_FEE_BASE_CENTS = 25
RECEIVING_FEE_EXTRA_PER_CHUNK_CENTS = 1
RECEIVING_FEE_CHUNK_UNITS = 20  # +1¢ per this many units after the first

# Phase 9A — geography gates for inter-island shipping.
# Inter-island shipments must originate at a completed ``dock`` plot the
# shipper owns AND deliver to a completed ``dock`` plot owned by some party
# (delivery dock owner gets the receiving fee — incentive to build coastal
# infrastructure). The shipper must also own at least one ``vessel`` material
# unit at dispatch time (Primitive 4 — vessels are real transport assets).
# Fuel: every voyage burns ``MOVEMENT_FUEL_TILES_PER_UNIT`` tiles of distance
# per unit of energy material consumed from the shipper's stockpile at the
# origin plot. Coal preferred; electricity falls back.
MOVEMENT_FUEL_TILES_PER_UNIT: int = 20
INTER_ISLAND_FUEL_MATERIALS: tuple[str, ...] = ("coal", "electricity")

# Phase 10B — uncharted voyages (no registered operator on the lane).
UNCHARTED_TIME_MULTIPLIER: Final[float] = 2.0
UNCHARTED_FUEL_MULTIPLIER: Final[float] = 2.0
# Legacy alias — fee premium is now UNCHARTED_TRIP_MULTIPLIER on trip cost.
UNCHARTED_FEE_MULTIPLIER: Final[float] = UNCHARTED_TRIP_MULTIPLIER


def _inter_island_allows_small_vessel(
    world: World, from_plot_id: PlotId, to_plot_id: PlotId
) -> bool:
    """True when neither endpoint sits on a classified *continent* landmass.

    Legacy worlds without ``landmass_type`` use full-size ``vessel`` only.
    """
    if not world.landmass_type:
        return False
    for pid in (from_plot_id, to_plot_id):
        lid = (world.landmass_id or {}).get(str(pid))
        if lid is None:
            return False
        t = world.landmass_type.get(int(lid))
        if t == "continent":
            return False
    return True


def receiving_fee_cents(qty: int) -> int:
    """Deterministic handling fee for a delivered shipment size."""
    if qty <= 0:
        return 0
    return RECEIVING_FEE_BASE_CENTS + max(0, qty - 1) // RECEIVING_FEE_CHUNK_UNITS * RECEIVING_FEE_EXTRA_PER_CHUNK_CENTS


def _is_ocean_route(world: World, from_plot_id: PlotId, to_plot_id: PlotId) -> bool:
    from realm.world.islands import is_inter_island_shipment

    return is_inter_island_shipment(world, from_plot_id, to_plot_id)


def _best_route_operator(world: World, from_plot_id: PlotId, to_plot_id: PlotId) -> tuple[dict | None, str | None]:
    """Cheapest registered operator for the region pair, if any."""
    from_region = region_for_plot(world, from_plot_id)
    to_region = region_for_plot(world, to_plot_id)
    if not from_region or not to_region or from_region == to_region:
        return (None, None)
    key = route_key(from_region, to_region)
    return (find_cheapest_operator(world, key), key)


def compute_shipping_fee(
    world: World,
    from_plot_id: PlotId,
    to_plot_id: PlotId,
    qty: int,
) -> dict:
    """Preview or compute bulk shipping economics for a lane.

    Returns ``total_fee_cents``, ``per_unit_cents``, ``trip_cost_cents``, and
    route metadata. Trip cost is fixed for any quantity — larger shipments
    amortize it.
    """
    from_plot = world.plots.get(from_plot_id)
    to_plot = world.plots.get(to_plot_id)
    if from_plot is None or to_plot is None:
        return {"ok": False, "reason": "plot not found"}

    dist = manhattan(world, from_plot_id, to_plot_id)
    is_ocean = _is_ocean_route(world, from_plot_id, to_plot_id)
    ocean_mult = OCEAN_TILE_MULTIPLIER if is_ocean else 1.0

    operator, rk = _best_route_operator(world, from_plot_id, to_plot_id)
    is_uncharted = operator is None and rk is not None
    uncharted_mult = UNCHARTED_TRIP_MULTIPLIER if is_uncharted else 1.0

    if operator and int(operator.get("fee_per_tile_cents", 999)) < PER_TILE_TRIP_FEE_CENTS:
        effective_per_tile = int(operator["fee_per_tile_cents"])
    else:
        effective_per_tile = PER_TILE_TRIP_FEE_CENTS

    trip_cost = int(
        (BASE_TRIP_FEE_CENTS + dist * effective_per_tile) * ocean_mult * uncharted_mult
    )
    ship_qty = max(1, int(qty))
    per_unit = max(MIN_PER_UNIT_FEE_CENTS, trip_cost // ship_qty)
    total_fee = per_unit * ship_qty

    op_party = str(operator.get("operator_party", "")) if operator else None
    breakeven = (
        int(trip_cost / max(1, per_unit - MIN_PER_UNIT_FEE_CENTS + 1)) + 1
        if per_unit > MIN_PER_UNIT_FEE_CENTS
        else 1
    )

    return {
        "ok": True,
        "trip_cost_cents": trip_cost,
        "per_unit_cents": per_unit,
        "total_fee_cents": total_fee,
        "distance_tiles": dist,
        "qty": ship_qty,
        "is_ocean": is_ocean,
        "is_uncharted": is_uncharted,
        "operator": op_party,
        "operator_party": op_party,
        "route_key": rk,
        "breakeven_qty": breakeven,
    }


def should_ship_goods(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    from_pid: PlotId,
    to_pid: PlotId,
    *,
    min_profit_cents: int = 5,
) -> bool:
    """True when shipping ``qty`` of ``material`` beats market price by ``min_profit_cents``/unit."""
    from realm.agents.market_oracle import get_oracle

    fee = compute_shipping_fee(world, from_pid, to_pid, qty)
    if not fee.get("ok"):
        return False
    oracle = get_oracle(world)
    sell_price = int(oracle.best_bid.get(str(material)) or 0)
    if sell_price <= 0:
        sell_price = int(oracle.best_ask.get(str(material), 0) or 0)
    per_unit_profit = sell_price - int(fee["per_unit_cents"])
    return per_unit_profit > int(min_profit_cents)


def _plot_owned(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


def _plot_has_completed_building(
    world: World, plot_id: PlotId, building_id: str, *, owner: PartyId | None = None
) -> bool:
    """True if the plot has a *completed* building of the given kind.

    When ``owner`` is supplied, also require the building to be owned by that
    party (used for the origin-dock check). Destination docks may be owned by
    anyone — the receiving-fee credit goes to whoever does own it.
    """
    pid_str = str(plot_id)
    for b in world.plot_buildings:
        if str(b.get("plot_id")) != pid_str:
            continue
        if str(b.get("building_id")) != building_id:
            continue
        if int(b.get("completes_at_tick", 0)) > int(world.tick):
            continue
        if owner is not None and str(b.get("party")) != str(owner):
            continue
        return True
    return False


def _plot_building_owner(
    world: World, plot_id: PlotId, building_id: str
) -> PartyId | None:
    """Owner of a completed building on the plot (None if not built / unfinished)."""
    pid_str = str(plot_id)
    for b in world.plot_buildings:
        if str(b.get("plot_id")) != pid_str:
            continue
        if str(b.get("building_id")) != building_id:
            continue
        if int(b.get("completes_at_tick", 0)) > int(world.tick):
            continue
        owner = b.get("party")
        return PartyId(str(owner)) if owner else None
    return None


def _inter_island_fuel_plan(
    world: World, party: PartyId, distance_tiles: int
) -> tuple[MaterialId, int] | None:
    """Pick a fuel material the party has enough of for an inter-island voyage.

    Returns ``(material_id, units_required)`` or ``None`` when neither coal
    nor electricity is on hand in sufficient quantity. Coal is preferred
    (cheaper, denser); electricity is the fallback (modern dockside power).
    """
    needed = max(1, distance_tiles // MOVEMENT_FUEL_TILES_PER_UNIT)
    for fuel in INTER_ISLAND_FUEL_MATERIALS:
        mid = MaterialId(fuel)
        if world.inventory.qty(party, mid) >= needed:
            return (mid, needed)
    return None


def dispatch_shipment(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    from_plot_id: PlotId,
    to_plot_id: PlotId,
) -> dict:
    """
    Ship goods between plots the party owns; fee to system; arrives after distance-based ticks.

    Returns {ok: True, shipment_id, arrive_tick, fee_cents} | {ok: False, reason}.
    """
    if qty <= 0:
        return {"ok": False, "reason": "quantity must be positive"}
    # Phase 9A — inter-island shipping is "merchant-to-port": the shipper
    # must own the origin plot, but the destination only needs to have a
    # completed dock (any owner). This unlocks shipping-as-a-service: you
    # can deliver to a customer's port without owning their land. Intra-
    # island still requires both endpoints to be the shipper's (door-to-
    # door wagon analog — no port to take consignment).
    from realm.world.islands import is_inter_island_shipment as _is_inter

    inter_island_preview = _is_inter(world, from_plot_id, to_plot_id)
    if not _plot_owned(world, party, from_plot_id):
        return {"ok": False, "reason": "must own origin plot"}
    if not inter_island_preview and not _plot_owned(world, party, to_plot_id):
        return {"ok": False, "reason": "intra-island shipping requires owning both plots"}
    if from_plot_id == to_plot_id:
        return {"ok": False, "reason": "same plot"}
    inv_q = world.inventory.qty(party, material)
    if inv_q < qty:
        return {"ok": False, "reason": "insufficient material"}
    dist = manhattan(world, from_plot_id, to_plot_id)
    from_region = region_for_plot(world, from_plot_id)
    to_region = region_for_plot(world, to_plot_id)
    # Phase 7A: inter-island shipments cost 2× per-tile (open-ocean modifier).
    inter_island = inter_island_preview
    # Phase 9A: inter-island shipping requires real coastal infrastructure.
    # - Origin plot must have a completed dock owned by the shipper.
    # - Destination plot must have a completed dock owned by *someone* (the
    #   dock owner gets the receiving fee on arrival).
    # - Shipper must own at least one cargo vessel (Primitive 4 — vessels are
    #   real assets; without one the open ocean is impassable).
    # - The voyage burns fuel: 1 unit of coal or electricity per
    #   ``MOVEMENT_FUEL_TILES_PER_UNIT`` tiles (Law 4 — energy required).
    inter_island_fuel: tuple[MaterialId, int] | None = None
    dest_dock_owner: PartyId | None = None
    if inter_island:
        if not _plot_has_completed_building(world, from_plot_id, "dock", owner=party):
            return {
                "ok": False,
                "reason": "inter-island shipping requires a completed dock at the origin plot",
            }
        dest_dock_owner = _plot_building_owner(world, to_plot_id, "dock")
        if dest_dock_owner is None:
            return {
                "ok": False,
                "reason": "inter-island shipping requires a completed dock at the destination plot",
            }
        has_vessel = world.inventory.qty(party, MaterialId("vessel")) >= 1
        has_small = world.inventory.qty(party, MaterialId("small_vessel")) >= 1
        if not has_vessel and not (has_small and _inter_island_allows_small_vessel(world, from_plot_id, to_plot_id)):
            return {
                "ok": False,
                "reason": "inter-island shipping requires a cargo vessel (or small_vessel on non-continent lanes)",
            }
        inter_island_fuel = _inter_island_fuel_plan(world, party, dist)
        if inter_island_fuel is None:
            return {
                "ok": False,
                "reason": "inter-island voyage requires coal or electricity for fuel",
            }
    # Phase 8D: refuse dispatch on a route that's currently blockaded by a storm.
    if inter_island:
        from realm.economy.market_events import is_route_blocked

        mapping = world.scenario_state.get("plot_islands") or {}
        from_isl = mapping.get(str(from_plot_id))
        to_isl = mapping.get(str(to_plot_id))
        if from_isl is not None and to_isl is not None:
            a, b = sorted([int(from_isl), int(to_isl)])
            simple_key = f"island_{a}|island_{b}"
            if is_route_blocked(world, simple_key):
                return {
                    "ok": False,
                    "reason": f"route {simple_key} closed by severe weather",
                }
    fee_info = compute_shipping_fee(world, from_plot_id, to_plot_id, qty)
    if not fee_info.get("ok"):
        return fee_info
    fee = int(fee_info["total_fee_cents"])
    op_route_key = fee_info.get("route_key")
    # Fuel/time penalties still apply only on inter-island uncharted lanes.
    uncharted_voyage = bool(fee_info.get("is_uncharted") and inter_island)
    operator_payee: PartyId | None = None
    op_party = fee_info.get("operator_party")
    if op_party and str(op_party) != str(party):
        operator_payee = PartyId(str(op_party))

    if op_route_key:
        from realm.infrastructure.route_operators import ROUTE_DAILY_CAPACITY

        vol = world.scenario_state.setdefault("route_daily_volume", {})
        route_data = vol.setdefault(
            str(op_route_key),
            {"daily_capacity": ROUTE_DAILY_CAPACITY, "units_shipped_today": 0},
        )
        today_vol = int(route_data.get("units_shipped_today", 0))
        capacity = int(route_data.get("daily_capacity", ROUTE_DAILY_CAPACITY))
        if today_vol + qty > capacity * 1.5:
            return {
                "ok": False,
                "reason": (
                    f"Route {op_route_key} is congested today (capacity: {capacity} units). "
                    "Try tomorrow or use an alternative route."
                ),
            }
        if today_vol + qty > capacity:
            fee = int(fee * 1.5)
            log_event(
                world,
                "route_congestion",
                f"Route {op_route_key} congested — surcharge applied",
                route_key=op_route_key,
                surcharge_pct=50,
            )
        route_data["units_shipped_today"] = today_vol + qty

    from realm.production.recipe_sites import plot_is_coastal
    from realm.infrastructure.roads import compute_road_savings_and_tolls
    from realm.economy.markets import best_resting_ask_cents, best_resting_bid_cents

    coastal_route = False
    from_plot = world.plots.get(from_plot_id)
    to_plot = world.plots.get(to_plot_id)
    if from_plot is not None and to_plot is not None:
        coastal_route = plot_is_coastal(world, from_plot) and plot_is_coastal(world, to_plot)
    unit_value = best_resting_ask_cents(world, material)
    if unit_value is None or unit_value <= 0:
        unit_value = best_resting_bid_cents(world, material)
    if unit_value is None or unit_value <= 0:
        unit_value = 100
    goods_value_cents = int(unit_value) * int(qty)
    road_calc = compute_road_savings_and_tolls(
        world,
        from_plot_id=from_plot_id,
        to_plot_id=to_plot_id,
        per_tile_cents=PER_TILE_TRIP_FEE_CENTS,
        goods_value_cents=goods_value_cents,
        shipper=party,
    )
    road_savings: int = int(road_calc["savings_cents"])
    tolls: list[tuple[PartyId, str, int]] = list(road_calc["tolls"])
    fee = max(BASE_TRIP_FEE_CENTS, fee - road_savings)
    total_toll_cents = sum(amt for _, _, amt in tolls)
    ocean_mult: float = OCEAN_TILE_MULTIPLIER if inter_island else 1.0
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < fee + total_toll_cents:
        return {"ok": False, "reason": "insufficient cash for shipping"}
    if operator_payee is not None:
        op_cash = party_cash_account(operator_payee)
        world.ledger.ensure_account(op_cash)
        pay = world.ledger.transfer(debit=cash, credit=op_cash, amount_cents=fee)
    else:
        pay = world.ledger.transfer(
            debit=cash,
            credit=system_reserve_account(),
            amount_cents=fee,
        )
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}
    if operator_payee is not None and op_route_key is not None:
        record_route_fee_collected(world, operator_payee, op_route_key, fee)
    # Sprint 6 — Phase A.4: track shipment count per region pair (used by
    # Frontier Roads Co. to pick high-traffic corridors to build).
    if from_region and to_region and from_region != to_region:
        key = route_key(from_region, to_region)
        counts = world.scenario_state.setdefault("route_shipment_counts", {})
        if isinstance(counts, dict):
            counts[str(key)] = int(counts.get(str(key), 0)) + 1
    # Sprint 6 — Phase A: pay tolls to each road owner along the path.
    tolls_paid: list[tuple[PartyId, str, int]] = []
    toll_failed = False
    for owner, segment_id, amount in tolls:
        if amount <= 0:
            continue
        owner_cash = party_cash_account(owner)
        world.ledger.ensure_account(owner_cash)
        tp = world.ledger.transfer(
            debit=cash, credit=owner_cash, amount_cents=int(amount)
        )
        if isinstance(tp, MoneyErr):
            toll_failed = True
            break
        tolls_paid.append((owner, segment_id, int(amount)))
        log_event(
            world,
            "road_toll_paid",
            f"{party} paid road toll on {segment_id} → {owner}: ${amount / 100:.2f}",
            party=str(party),
            owner=str(owner),
            segment_id=segment_id,
            amount_cents=int(amount),
            material=str(material),
            qty=qty,
        )

    def _refund_tolls() -> None:
        for owner, _sid, amount in tolls_paid:
            world.ledger.transfer(
                debit=party_cash_account(owner), credit=cash, amount_cents=int(amount)
            )

    def _refund_fee() -> None:
        _refund_tolls()
        if operator_payee is not None:
            world.ledger.transfer(
                debit=party_cash_account(operator_payee), credit=cash, amount_cents=fee
            )
        else:
            world.ledger.transfer(
                debit=system_reserve_account(), credit=cash, amount_cents=fee
            )

    if toll_failed:
        _refund_fee()
        return {"ok": False, "reason": "toll payment failed"}

    # Phase 9A: burn fuel for inter-island voyages (Law 4). Refund the fee
    # bundle if the inventory pull fails — we shouldn't have charged the
    # shipper without consuming the fuel.
    # Phase 10B — uncharted voyages burn 2x the fuel (UNCHARTED_FUEL_MULTIPLIER).
    fuel_consumed: tuple[MaterialId, int] | None = None
    if inter_island_fuel is not None:
        fuel_mid, fuel_units = inter_island_fuel
        if uncharted_voyage:
            fuel_units = max(1, int(fuel_units * UNCHARTED_FUEL_MULTIPLIER))
            if world.inventory.qty(party, fuel_mid) < fuel_units:
                _refund_fee()
                return {
                    "ok": False,
                    "reason": "uncharted voyage requires extra fuel (2x normal)",
                }
        rm_fuel = world.inventory.remove(party, fuel_mid, fuel_units)
        if isinstance(rm_fuel, MatterErr):
            _refund_fee()
            return {"ok": False, "reason": rm_fuel.reason}
        fuel_consumed = (fuel_mid, fuel_units)

    def _refund_fuel() -> None:
        if fuel_consumed is None:
            return
        fmid, fqty = fuel_consumed
        world.inventory.add(party, fmid, fqty)

    rm = world.inventory.remove(party, material, qty)
    if isinstance(rm, MatterErr):
        _refund_fuel()
        _refund_fee()
        return {"ok": False, "reason": rm.reason}
    # Sprint 3 — Phase D.3: harbor speed bonus. A dispatch from a coastal plot
    # that has a completed ``dock`` building moves at 1.5 × normal speed.
    transit_ticks = dist * TRANSIT_TICKS_PER_TILE + TRANSIT_BASE_TICKS
    has_dock_at_origin = any(
        str(b.get("plot_id")) == str(from_plot_id)
        and str(b.get("building_id")) == "dock"
        and int(b.get("completes_at_tick", 0)) <= int(world.tick)
        for b in world.plot_buildings
    )
    if has_dock_at_origin and from_plot is not None and plot_is_coastal(world, from_plot):
        # 1.5× speed → travel time × (10000 / 15000) = × 0.667
        transit_ticks = max(1, transit_ticks * 10_000 // (10_000 + HARBOR_TRANSIT_SPEEDUP_BPS))
    # Phase 10B — uncharted voyage takes 2x the time (UNCHARTED_TIME_MULTIPLIER).
    # Applied AFTER the harbor bonus so the speedup still helps; the explorer
    # still loses on net relative to a charted route.
    if uncharted_voyage:
        transit_ticks = max(1, int(transit_ticks * UNCHARTED_TIME_MULTIPLIER))
    arrive = world.tick + transit_ticks
    world.next_shipment_seq += 1
    sid = f"ship-{world.next_shipment_seq}"
    # Phase 9A — stash inter-island metadata onto the InTransit row so
    # ``deliver_transit`` knows where to credit the receiving fee.
    world.in_transit.append(
        InTransit(
            shipment_id=sid,
            party=party,
            material=material,
            qty=qty,
            dest_plot_id=to_plot_id,
            arrive_tick=arrive,
            from_plot_id=from_plot_id,
            dest_dock_owner=(
                str(dest_dock_owner) if dest_dock_owner is not None else None
            ),
            inter_island=bool(inter_island),
            route_key=op_route_key,
            uncharted=bool(uncharted_voyage),
        )
    )
    fuel_log = (
        {"material": str(fuel_consumed[0]), "units": int(fuel_consumed[1])}
        if fuel_consumed is not None
        else None
    )
    log_event(
        world,
        "ship_dispatch",
        f"{party} shipped {qty}×{material} → {to_plot_id} (arrive tick {arrive}, fee ${fee / 100:.2f}"
        + (f", route {op_route_key} → {operator_payee}" if operator_payee is not None else "")
        + (
            f", fuel {fuel_log['units']} {fuel_log['material']}"
            if fuel_log is not None
            else ""
        )
        + (", uncharted" if uncharted_voyage else "")
        + ")",
        party=str(party),
        material=str(material),
        qty=qty,
        dest_plot_id=str(to_plot_id),
        arrive_tick=arrive,
        fee_cents=fee,
        route_key=op_route_key,
        operator_party=str(operator_payee) if operator_payee is not None else None,
        inter_island=bool(inter_island),
        uncharted=bool(uncharted_voyage),
        dest_dock_owner=str(dest_dock_owner) if dest_dock_owner is not None else None,
        fuel_material=fuel_log["material"] if fuel_log is not None else None,
        fuel_units=fuel_log["units"] if fuel_log is not None else 0,
    )
    if uncharted_voyage and op_route_key is not None:
        log_event(
            world,
            "voyage_uncharted",
            f"{party} embarked on an uncharted voyage on {op_route_key} (no operator registered).",
            party=str(party),
            route_key=op_route_key,
            fee_cents=fee,
            transit_ticks=transit_ticks,
        )
    return {
        "ok": True,
        "shipment_id": sid,
        "arrive_tick": arrive,
        "fee_cents": fee,
        "route_key": op_route_key,
        "operator_party": str(operator_payee) if operator_payee is not None else None,
        "coastal_route": bool(coastal_route),
        "harbor_speedup": bool(
            from_plot is not None and has_dock_at_origin and plot_is_coastal(world, from_plot)
        ),
        "road_savings_cents": int(road_savings),
        "road_tolls_paid_cents": int(total_toll_cents),
        "road_segments_used": [s for _, s, _ in tolls_paid],
        "inter_island": bool(inter_island),
        "ocean_modifier_mult": int(ocean_mult),
        "dest_dock_owner": str(dest_dock_owner) if dest_dock_owner is not None else None,
        "fuel_material": fuel_log["material"] if fuel_log is not None else None,
        "fuel_units": fuel_log["units"] if fuel_log is not None else 0,
    }


def deliver_transit(world: World) -> None:
    """Deliver shipments whose arrive_tick is <= current tick (before tick increments)."""
    t = world.tick
    keep: list[InTransit] = []
    for s in world.in_transit:
        if s.arrive_tick > t:
            keep.append(s)
            continue
        recv_fee = receiving_fee_cents(s.qty)
        cash = party_cash_account(s.party)
        if recv_fee > 0 and world.ledger.balance(cash) < recv_fee:
            keep.append(s)
            log_event(
                world,
                "ship_deliver_blocked",
                f"{s.party} could not pay receiving fee {recv_fee}¢ for {s.shipment_id} — shipment held",
                party=str(s.party),
                shipment_id=s.shipment_id,
                receiving_fee_cents=recv_fee,
            )
            continue
        # Sprint 6 — Phase D.1: matter always lands in party inventory; the
        # destination's plot_output_stock is updated as a display-only log when
        # plot logistics is enabled.
        ad = try_add_inventory(world, s.party, s.material, s.qty)
        if isinstance(ad, MatterErr):
            keep.append(s)
            continue
        if recv_fee > 0:
            # Phase 9A — inter-island receiving fee credits the destination
            # dock owner. Intra-island shipments still sink to system_reserve
            # because they don't dock (door-to-door wagon analog). The dock
            # owner falls back to system_reserve if the destination dock
            # owner is absent (defensive — should never happen because we
            # gated dispatch on a completed dock).
            dock_owner_str = getattr(s, "dest_dock_owner", None)
            inter_island_flag = bool(getattr(s, "inter_island", False))
            if inter_island_flag and dock_owner_str:
                receiver_acct = party_cash_account(PartyId(str(dock_owner_str)))
                world.ledger.ensure_account(receiver_acct)
                pay_recv = world.ledger.transfer(
                    debit=cash,
                    credit=receiver_acct,
                    amount_cents=recv_fee,
                )
            else:
                pay_recv = world.ledger.transfer(
                    debit=cash,
                    credit=system_reserve_account(),
                    amount_cents=recv_fee,
                )
            if isinstance(pay_recv, MoneyErr):
                rb2 = world.inventory.remove(s.party, s.material, s.qty)
                assert not isinstance(rb2, MatterErr)
                keep.append(s)
                continue
        if world.use_plot_output_logistics:
            bucket = world.plot_output_stock.setdefault(str(s.dest_plot_id), {})
            bucket[str(s.material)] = int(bucket.get(str(s.material), 0)) + int(s.qty)
        # Phase 10B — record the voyage on its route_key so NPC shippers
        # (or Phase 11 player UI) can identify high-traffic uncharted lanes
        # and register a regular operator.
        rk = getattr(s, "route_key", None)
        if rk:
            world.voyage_history[str(rk)] = int(world.voyage_history.get(str(rk), 0)) + 1
            record_route_voyage_completed(world, str(rk))
        log_event(
            world,
            "ship_deliver",
            f"Delivered {s.qty}×{s.material} to {s.party} at {s.dest_plot_id} (receiving {recv_fee}¢)",
            party=str(s.party),
            material=str(s.material),
            qty=s.qty,
            dest_plot_id=str(s.dest_plot_id),
            shipment_id=s.shipment_id,
            receiving_fee_cents=recv_fee,
            route_key=rk,
            uncharted=bool(getattr(s, "uncharted", False)),
        )
    world.in_transit = keep

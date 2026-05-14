"""Goods in transit — Law 3 (time + distance).

Shipping fee (integer cents): ``BASE_SHIP_FEE_CENTS + manhattan(from, to) * per_tile``.

When a registered route operator exists for the two regions the shipment crosses,
``per_tile`` is that operator's ``fee_per_tile_cents`` (cheapest wins) and the
entire fee is credited to them. Otherwise the fee falls back to the legacy
``PER_TILE_SHIP_CENTS`` and is credited to ``system:reserve`` (sink).

Phase 7A — inter-island shipments (origin and destination on *different*
landmasses in the genesis four-island layout) pay a ``2×`` open-ocean
modifier on the per-tile portion of the fee. Land movement across ocean
tiles is impassable (``tile_movement_cost == math.inf``).

Arrival tick uses Manhattan distance × ``TRANSIT_TICKS_PER_TILE`` (game-minutes
per tile) plus ``TRANSIT_BASE_TICKS`` handling.
"""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.world.geo import manhattan
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.plot_logistics import plot_output_qty, remove_plot_output, try_add_plot_output, uses_plot_logistics
from realm.world.regions import region_for_plot, route_key
from realm.route_operators import find_cheapest_operator, record_route_fee_collected
from realm.storage_caps import try_add_inventory
from realm.core.time_scale import TRANSIT_BASE_TICKS, TRANSIT_TICKS_PER_TILE
from realm.world import InTransit, World

BASE_SHIP_FEE_CENTS = 100
PER_TILE_SHIP_CENTS = 50

# Sprint 3 — Phase D.2/D.3: coastal advantages.
COASTAL_ROUTE_DISCOUNT_BPS: int = 4_000  # 40 % discount → multiplier 0.60
HARBOR_TRANSIT_SPEEDUP_BPS: int = 5_000  # 50 % faster departure from dock plots

# Unloading / receiving (dock handling): paid when goods are accepted at destination; all parties alike.
RECEIVING_FEE_BASE_CENTS = 25
RECEIVING_FEE_EXTRA_PER_CHUNK_CENTS = 1
RECEIVING_FEE_CHUNK_UNITS = 20  # +1¢ per this many units after the first


def receiving_fee_cents(qty: int) -> int:
    """Deterministic handling fee for a delivered shipment size."""
    if qty <= 0:
        return 0
    return RECEIVING_FEE_BASE_CENTS + max(0, qty - 1) // RECEIVING_FEE_CHUNK_UNITS * RECEIVING_FEE_EXTRA_PER_CHUNK_CENTS


def _plot_owned(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


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
    if not _plot_owned(world, party, from_plot_id) or not _plot_owned(world, party, to_plot_id):
        return {"ok": False, "reason": "must own both plots"}
    if from_plot_id == to_plot_id:
        return {"ok": False, "reason": "same plot"}
    inv_q = world.inventory.qty(party, material)
    if inv_q < qty:
        return {"ok": False, "reason": "insufficient material"}
    dist = manhattan(world, from_plot_id, to_plot_id)
    from_region = region_for_plot(world, from_plot_id)
    to_region = region_for_plot(world, to_plot_id)
    # Phase 7A: inter-island shipments cost 2× per-tile (open-ocean modifier).
    from realm.world.islands import is_inter_island_shipment

    inter_island = is_inter_island_shipment(world, from_plot_id, to_plot_id)
    ocean_mult = 2 if inter_island else 1
    operator_payee: PartyId | None = None
    op_route_key: str | None = None
    if from_region and to_region and from_region != to_region:
        key = route_key(from_region, to_region)
        op_route_key = key
        op = find_cheapest_operator(world, key)
        if op is not None and str(op.get("operator_party")) != str(party):
            # An operator other than the shipper themselves: credit them the fee.
            operator_payee = PartyId(str(op["operator_party"]))
            per_tile = max(1, int(op.get("fee_per_tile_cents", PER_TILE_SHIP_CENTS))) * ocean_mult
            fee = BASE_SHIP_FEE_CENTS + dist * per_tile
        else:
            fee = BASE_SHIP_FEE_CENTS + dist * PER_TILE_SHIP_CENTS * ocean_mult
    else:
        fee = BASE_SHIP_FEE_CENTS + dist * PER_TILE_SHIP_CENTS * ocean_mult
    # Sprint 3 — Phase D.2: 40 % discount for coastal → coastal lanes.
    from realm.recipe_sites import plot_is_coastal

    coastal_route = False
    from_plot = world.plots.get(from_plot_id)
    to_plot = world.plots.get(to_plot_id)
    if from_plot is not None and to_plot is not None:
        coastal_route = plot_is_coastal(world, from_plot) and plot_is_coastal(world, to_plot)
    if coastal_route:
        fee = max(BASE_SHIP_FEE_CENTS, fee * (10_000 - COASTAL_ROUTE_DISCOUNT_BPS) // 10_000)
    # Sprint 6 — Phase A: roads on the deterministic A→B path cut the per-tile
    # cost by 50% on covered tiles and optionally collect ad-valorem tolls for
    # the road owners.
    from realm.roads import compute_road_savings_and_tolls
    from realm.markets import best_resting_ask_cents, best_resting_bid_cents

    per_tile_effective = (
        max(1, int(op.get("fee_per_tile_cents", PER_TILE_SHIP_CENTS)))
        if operator_payee is not None
        else PER_TILE_SHIP_CENTS
    )
    per_tile_effective *= ocean_mult
    if coastal_route:
        per_tile_effective = (
            per_tile_effective * (10_000 - COASTAL_ROUTE_DISCOUNT_BPS) // 10_000
        )
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
        per_tile_cents=per_tile_effective,
        goods_value_cents=goods_value_cents,
        shipper=party,
    )
    road_savings: int = int(road_calc["savings_cents"])
    tolls: list[tuple[PartyId, str, int]] = list(road_calc["tolls"])
    fee = max(BASE_SHIP_FEE_CENTS, fee - road_savings)
    total_toll_cents = sum(amt for _, _, amt in tolls)
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

    rm = world.inventory.remove(party, material, qty)
    if isinstance(rm, MatterErr):
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
    arrive = world.tick + transit_ticks
    world.next_shipment_seq += 1
    sid = f"ship-{world.next_shipment_seq}"
    world.in_transit.append(
        InTransit(
            shipment_id=sid,
            party=party,
            material=material,
            qty=qty,
            dest_plot_id=to_plot_id,
            arrive_tick=arrive,
            from_plot_id=from_plot_id,
        )
    )
    log_event(
        world,
        "ship_dispatch",
        f"{party} shipped {qty}×{material} → {to_plot_id} (arrive tick {arrive}, fee ${fee / 100:.2f}"
        + (f", route {op_route_key} → {operator_payee}" if operator_payee is not None else "")
        + ")",
        party=str(party),
        material=str(material),
        qty=qty,
        dest_plot_id=str(to_plot_id),
        arrive_tick=arrive,
        fee_cents=fee,
        route_key=op_route_key,
        operator_party=str(operator_payee) if operator_payee is not None else None,
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
        )
    world.in_transit = keep

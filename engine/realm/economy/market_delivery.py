"""Physical settlement for order-book fills — DDP (seller ships) and FOB (buyer picks up)."""

from __future__ import annotations

from dataclasses import dataclass

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr, MatterOk, MatterResult
from realm.events.event_log import log_event
from realm.core.ledger import MoneyErr, party_cash_account
from realm.economy.market_reserves import consume_reserve_for_order
from realm.infrastructure.plot_logistics import (
    add_party_plot_stock,
    owned_plot_ids_sorted,
    remove_plot_output,
)
from realm.production.storage_caps import (
    is_carried_material,
    party_uses_plot_storage,
    plot_has_active_warehouse,
    try_add_inventory,
)
from realm.world import World

DELIVERY_DDP: str = "ddp"
DELIVERY_FOB: str = "fob"
VALID_DELIVERY_TERMS: frozenset[str] = frozenset({DELIVERY_DDP, DELIVERY_FOB})

# Seller breach when DDP dispatch fails after a match — paid to buyer (trade rolls back).
DDP_BREACH_PENALTY_BPS: int = 2_000  # 20% of line value
DDP_BREACH_MIN_CENTS: int = 500
# Uncollected FOB rows are capped so per-tick scans stay bounded on long runs.
FOB_PICKUP_MAX_ROWS: int = 4_000
FOB_PICKUP_MAX_AGE_TICKS: int = 14 * 1_440  # 14 game-days


@dataclass(frozen=True, slots=True)
class MarketFobPickup:
    pickup_id: str
    buyer: PartyId
    seller: PartyId
    from_plot_id: PlotId
    material: MaterialId
    qty: int
    quality: str
    match_tick: int
    order_id: str = ""


def apply_ddp_breach_penalty(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    trade_value_cents: int,
) -> int:
    """Charge seller for failing DDP after match; compensates buyer. Returns cents paid."""
    trade_value_cents = max(0, int(trade_value_cents))
    penalty = max(
        DDP_BREACH_MIN_CENTS,
        trade_value_cents * DDP_BREACH_PENALTY_BPS // 10_000,
    )
    seller_c = party_cash_account(seller)
    buyer_c = party_cash_account(buyer)
    if world.ledger.balance(seller_c) < penalty:
        penalty = max(0, world.ledger.balance(seller_c))
    if penalty <= 0:
        log_event(
            world,
            "market_ddp_breach_unpaid",
            f"{seller} breached DDP but has no cash for {penalty}¢ penalty",
            seller=str(seller),
            buyer=str(buyer),
        )
        return 0
    tr = world.ledger.transfer(debit=seller_c, credit=buyer_c, amount_cents=penalty)
    if isinstance(tr, MoneyErr):
        return 0
    log_event(
        world,
        "market_ddp_breach",
        f"{seller} paid {penalty}¢ breach penalty to {buyer} (DDP delivery failed)",
        seller=str(seller),
        buyer=str(buyer),
        penalty_cents=penalty,
    )
    return penalty


def normalize_delivery_terms(raw: str | None) -> str:
    t = str(raw or DELIVERY_DDP).strip().lower()
    return t if t in VALID_DELIVERY_TERMS else DELIVERY_DDP


def resolve_buyer_delivery_plot(
    world: World,
    buyer: PartyId,
    *,
    explicit: PlotId | None = None,
) -> PlotId | None:
    """Buyer delivery point: explicit bid plot, else warehouse plot, else first owned."""
    owned = owned_plot_ids_sorted(world, buyer)
    if not owned:
        return None
    if explicit is not None and explicit in owned:
        return explicit
    for pid in owned:
        if plot_has_active_warehouse(world, pid):
            return pid
    return owned[0]


def resolve_seller_list_plot(ask: object, seller: PartyId) -> PlotId | None:
    fp = str(getattr(ask, "from_plot_id", "") or "").strip()
    if fp:
        return PlotId(fp)
    return None


def _instant_carry_delivery(
    world: World,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    *,
    quality: str,
) -> MatterResult:
    if party_uses_plot_storage(world, buyer) and not is_carried_material(material):
        return add_party_plot_stock(world, buyer, material, qty)
    return try_add_inventory(world, buyer, material, qty, quality=quality)


def _fob_by_id(world: World) -> dict[str, MarketFobPickup]:
    cached = world.scenario_state.get("_fob_pickup_by_id")
    if isinstance(cached, dict) and len(cached) == len(world.market_fob_pickups):
        return cached
    rebuilt: dict[str, MarketFobPickup] = {
        str(p.pickup_id): p for p in world.market_fob_pickups
    }
    world.scenario_state["_fob_pickup_by_id"] = rebuilt
    by_buyer: dict[str, list[str]] = {}
    for p in world.market_fob_pickups:
        by_buyer.setdefault(str(p.buyer), []).append(str(p.pickup_id))
    world.scenario_state["_fob_pickup_ids_by_buyer"] = by_buyer
    return rebuilt


def _fob_ids_for_buyer(world: World, buyer: PartyId) -> list[str]:
    _fob_by_id(world)
    raw = world.scenario_state.get("_fob_pickup_ids_by_buyer") or {}
    return list(raw.get(str(buyer), ()))


def _register_fob_pickup(world: World, row: MarketFobPickup) -> None:
    world.market_fob_pickups.append(row)
    by_id = _fob_by_id(world)
    by_id[str(row.pickup_id)] = row
    by_buyer = world.scenario_state.setdefault("_fob_pickup_ids_by_buyer", {})
    by_buyer.setdefault(str(row.buyer), []).append(str(row.pickup_id))


def _unregister_fob_pickup(world: World, pickup_id: str) -> MarketFobPickup | None:
    by_id = _fob_by_id(world)
    row = by_id.pop(str(pickup_id), None)
    if row is None:
        return None
    buyer_ids = world.scenario_state.get("_fob_pickup_ids_by_buyer") or {}
    ids = buyer_ids.get(str(row.buyer))
    if ids is not None and pickup_id in ids:
        ids.remove(pickup_id)
    world.market_fob_pickups = [
        p for p in world.market_fob_pickups if str(p.pickup_id) != str(pickup_id)
    ]
    return row


def _trim_fob_pickup_backlog(world: World) -> None:
    """Drop oldest uncollected pickups so settler/NPC collection stays O(k) not O(n)."""
    if not world.market_fob_pickups:
        return
    cutoff = max(0, int(world.tick) - FOB_PICKUP_MAX_AGE_TICKS)
    stale = sorted(
        world.market_fob_pickups,
        key=lambda p: int(getattr(p, "match_tick", 0)),
    )
    to_drop: list[str] = []
    for row in stale:
        if int(getattr(row, "match_tick", 0)) < cutoff:
            to_drop.append(str(row.pickup_id))
    overflow = len(world.market_fob_pickups) - FOB_PICKUP_MAX_ROWS
    if overflow > 0:
        for row in stale:
            if len(to_drop) >= overflow:
                break
            pid = str(row.pickup_id)
            if pid not in to_drop:
                to_drop.append(pid)
    for pid in to_drop:
        row = _unregister_fob_pickup(world, pid)
        if row is None:
            continue
        log_event(
            world,
            "market_fob_expired",
            f"FOB pickup {pid} expired ({row.qty}×{row.material} at {row.from_plot_id})",
            pickup_id=pid,
            buyer=str(row.buyer),
            seller=str(row.seller),
            material=str(row.material),
            qty=int(row.qty),
        )


def tick_fob_pickup_hygiene(world: World) -> None:
    from realm.core.time_scale import TICKS_PER_GAME_DAY

    if int(world.tick) <= 0 or int(world.tick) % int(TICKS_PER_GAME_DAY) != 0:
        return
    _trim_fob_pickup_backlog(world)


def _append_fob_pickup(
    world: World,
    *,
    buyer: PartyId,
    seller: PartyId,
    from_plot_id: PlotId,
    material: MaterialId,
    qty: int,
    quality: str,
    order_id: str,
) -> MatterResult:
    world.next_market_pickup_seq = int(getattr(world, "next_market_pickup_seq", 0)) + 1
    pid = f"mpick-{world.next_market_pickup_seq}"
    row = MarketFobPickup(
        pickup_id=pid,
        buyer=buyer,
        seller=seller,
        from_plot_id=from_plot_id,
        material=material,
        qty=int(qty),
        quality=quality,
        match_tick=int(world.tick),
        order_id=str(order_id),
    )
    _register_fob_pickup(world, row)
    if len(world.market_fob_pickups) > FOB_PICKUP_MAX_ROWS:
        _trim_fob_pickup_backlog(world)
    log_event(
        world,
        "market_fob_pickup",
        f"{buyer} must collect {qty}×{material} at {from_plot_id} (FOB from {seller})",
        buyer=str(buyer),
        seller=str(seller),
        from_plot_id=str(from_plot_id),
        material=str(material),
        qty=int(qty),
        pickup_id=pid,
        order_id=str(order_id),
    )
    return MatterOk()


def _ddp_failure_allows_fob_fallback(reason: str) -> bool:
    """Seller-paid DDP paths that inland miners / cash-poor sellers cannot satisfy."""
    r = reason.lower()
    return any(
        frag in r
        for frag in (
            "dock at the origin",
            "dock at the destination",
            "insufficient cash for shipping",
            "cargo vessel",
            "inter-island voyage requires coal",
            "same plot",
        )
    )


def _instant_same_plot_delivery(
    world: World,
    *,
    buyer: PartyId,
    seller: PartyId,
    plot_id: PlotId,
    material: MaterialId,
    qty: int,
    order_id: str,
    escrowed: bool,
) -> MatterResult:
    """Zero-distance DDP: listing yard equals buyer delivery plot (no shipment row)."""
    if escrowed and order_id:
        cr = consume_reserve_for_order(world, order_id, int(qty))
        if isinstance(cr, MatterErr):
            return cr
    rm = remove_plot_output(world, seller, plot_id, material, qty)
    if isinstance(rm, MatterErr):
        return rm
    return add_party_plot_stock(world, buyer, material, qty)


def _finalize_fob_pickup(
    world: World,
    *,
    buyer: PartyId,
    seller: PartyId,
    from_plot: PlotId,
    material: MaterialId,
    qty: int,
    quality: str,
    order_id: str,
) -> MatterResult:
    fob = _append_fob_pickup(
        world,
        buyer=buyer,
        seller=seller,
        from_plot_id=from_plot,
        material=material,
        qty=qty,
        quality=quality,
        order_id=order_id,
    )
    if not isinstance(fob, MatterErr) and order_id:
        consume_reserve_for_order(world, order_id, int(qty))
    return fob


def fulfill_market_matter(
    world: World,
    *,
    buyer: PartyId,
    seller: PartyId,
    material: MaterialId,
    qty: int,
    ask: object,
    bid: object | None,
) -> MatterResult:
    """After payment: DDP spawns seller-paid transit; FOB creates pickup at listing plot."""
    if qty <= 0:
        return MatterOk()
    quality = str(getattr(ask, "quality", "standard"))
    if not party_uses_plot_storage(world, buyer) or is_carried_material(material):
        return _instant_carry_delivery(world, buyer, material, qty, quality=quality)

    from_plot = resolve_seller_list_plot(ask, seller)
    if from_plot is None:
        if not party_uses_plot_storage(world, seller):
            return _instant_carry_delivery(world, buyer, material, qty, quality=quality)
        return MatterErr(reason="sell order missing listing plot for physical delivery")

    terms = normalize_delivery_terms(getattr(ask, "delivery_terms", DELIVERY_DDP))
    order_id = str(getattr(ask, "order_id", "") or "")

    if terms == DELIVERY_FOB:
        return _finalize_fob_pickup(
            world,
            buyer=buyer,
            seller=seller,
            from_plot=from_plot,
            material=material,
            qty=int(qty),
            quality=quality,
            order_id=order_id,
        )

    dest_raw = str(getattr(bid, "delivery_plot_id", "") or "") if bid is not None else ""
    dest_explicit = PlotId(dest_raw) if dest_raw else None
    dest = resolve_buyer_delivery_plot(world, buyer, explicit=dest_explicit)
    if dest is None:
        return MatterErr(reason="buyer has no plot to receive delivery")

    from realm.infrastructure.movement import dispatch_shipment
    from realm.economy.market_reserves import uses_plot_market_reserve

    escrowed = bool(order_id and uses_plot_market_reserve(world, seller, material))

    if from_plot == dest:
        plot = world.plots.get(from_plot)
        if plot is not None and plot.owner == buyer and seller == buyer:
            ad = _instant_same_plot_delivery(
                world,
                buyer=buyer,
                seller=seller,
                plot_id=from_plot,
                material=material,
                qty=int(qty),
                order_id=order_id,
                escrowed=escrowed,
            )
            if not isinstance(ad, MatterErr):
                log_event(
                    world,
                    "market_ddp_same_plot",
                    f"{buyer} received {qty}×{material} on {from_plot} (zero-distance DDP)",
                    buyer=str(buyer),
                    seller=str(seller),
                    material=str(material),
                    qty=int(qty),
                    plot_id=str(from_plot),
                )
            return ad
        return _finalize_fob_pickup(
            world,
            buyer=buyer,
            seller=seller,
            from_plot=from_plot,
            material=material,
            qty=int(qty),
            quality=quality,
            order_id=order_id,
        )

    ship = dispatch_shipment(
        world,
        seller,
        material,
        int(qty),
        from_plot,
        dest,
        consignee=buyer,
        escrowed_market=escrowed,
    )
    if ship.get("ok"):
        log_event(
            world,
            "market_ddp_ship",
            f"{seller} shipping {qty}×{material} to {buyer} at {dest} (DDP)",
            seller=str(seller),
            buyer=str(buyer),
            material=str(material),
            qty=int(qty),
            from_plot_id=str(from_plot),
            dest_plot_id=str(dest),
            shipment_id=str(ship.get("shipment_id", "")),
        )
        if order_id:
            consume_reserve_for_order(world, order_id, int(qty))
        return MatterOk()

    reason = str(ship.get("reason", ""))
    if _ddp_failure_allows_fob_fallback(reason):
        log_event(
            world,
            "market_ddp_fob_fallback",
            f"DDP unavailable ({reason}) — FOB pickup at {from_plot} for {buyer}",
            seller=str(seller),
            buyer=str(buyer),
            material=str(material),
            qty=int(qty),
            reason=reason,
        )
        return _finalize_fob_pickup(
            world,
            buyer=buyer,
            seller=seller,
            from_plot=from_plot,
            material=material,
            qty=int(qty),
            quality=quality,
            order_id=order_id,
        )

    log_event(
        world,
        "market_ddp_failed",
        f"DDP failed ({reason}) — match void, breach penalty due",
        seller=str(seller),
        buyer=str(buyer),
        material=str(material),
        qty=int(qty),
        reason=reason,
    )
    return MatterErr(reason=f"DDP delivery failed: {reason}")


def pickup_fob(
    world: World,
    buyer: PartyId,
    pickup_id: str,
    *,
    to_plot_id: PlotId | None = None,
) -> dict:
    """Buyer arranges freight from the seller's listing plot (FOB)."""
    row = _fob_by_id(world).get(str(pickup_id))
    if row is None:
        return {"ok": False, "reason": "pickup not found"}
    if row.buyer != buyer:
        return {"ok": False, "reason": "not your pickup"}
    dest = resolve_buyer_delivery_plot(world, buyer, explicit=to_plot_id)
    if dest is None:
        return {"ok": False, "reason": "no destination plot"}
    if row.from_plot_id == dest:
        rm = remove_plot_output(world, row.seller, row.from_plot_id, row.material, int(row.qty))
        if isinstance(rm, MatterErr):
            return {"ok": False, "reason": rm.reason}
        ad = add_party_plot_stock(world, buyer, row.material, int(row.qty))
        if isinstance(ad, MatterErr):
            return {"ok": False, "reason": ad.reason}
        _unregister_fob_pickup(world, pickup_id)
        log_event(
            world,
            "market_fob_collected",
            f"{buyer} collected {row.qty}×{row.material} on {dest} (same-plot pickup)",
            buyer=str(buyer),
            seller=str(row.seller),
            pickup_id=pickup_id,
        )
        return {"ok": True, "dest_plot_id": str(dest)}
    from realm.infrastructure.movement import dispatch_shipment

    ship = dispatch_shipment(
        world,
        buyer,
        row.material,
        int(row.qty),
        row.from_plot_id,
        dest,
        consignee=buyer,
    )
    if not ship.get("ok"):
        return dict(ship)
    _unregister_fob_pickup(world, pickup_id)
    log_event(
        world,
        "market_fob_collected",
        f"{buyer} collected {row.qty}×{row.material} from {row.from_plot_id} → {dest}",
        buyer=str(buyer),
        seller=str(row.seller),
        pickup_id=pickup_id,
        shipment_id=str(ship.get("shipment_id", "")),
    )
    return {"ok": True, "shipment_id": ship.get("shipment_id"), "dest_plot_id": str(dest)}


def fulfill_p2p_delivery(
    world: World,
    *,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    from_plot_id: PlotId | None = None,
    to_plot_id: PlotId | None = None,
) -> MatterResult:
    """P2P bulk: ship from seller plot to buyer plot (no instant stash teleport)."""
    if qty <= 0:
        return MatterOk()
    if not party_uses_plot_storage(world, buyer) or is_carried_material(material):
        return try_add_inventory(world, buyer, material, qty)
    if not party_uses_plot_storage(world, seller):
        return MatterErr(reason="seller uses plot storage required for bulk P2P")
    from realm.infrastructure.plot_logistics import pick_plot_with_stock

    src = from_plot_id
    if src is None:
        src = pick_plot_with_stock(world, seller, material, qty)
    if src is None:
        return MatterErr(reason="seller has no uncommitted bulk on plots")
    dest = resolve_buyer_delivery_plot(world, buyer, explicit=to_plot_id)
    if dest is None:
        return MatterErr(reason="buyer has no plot to receive delivery")
    from realm.infrastructure.movement import dispatch_shipment

    ship = dispatch_shipment(
        world,
        seller,
        material,
        int(qty),
        src,
        dest,
        consignee=buyer,
    )
    if not ship.get("ok"):
        return MatterErr(reason=str(ship.get("reason", "dispatch failed")))
    log_event(
        world,
        "p2p_ship",
        f"{seller} shipping {qty}×{material} to {buyer} at {dest} (P2P)",
        seller=str(seller),
        buyer=str(buyer),
        material=str(material),
        qty=int(qty),
        shipment_id=str(ship.get("shipment_id", "")),
    )
    return MatterOk()


def fob_pickups_for_party(world: World, party: PartyId) -> list[dict]:
    out: list[dict] = []
    by_id = _fob_by_id(world)
    seen: set[str] = set()
    for pid in _fob_ids_for_buyer(world, party):
        p = by_id.get(pid)
        if p is None:
            continue
        seen.add(pid)
        out.append(
            {
                "pickup_id": p.pickup_id,
                "buyer": str(p.buyer),
                "seller": str(p.seller),
                "from_plot_id": str(p.from_plot_id),
                "material": str(p.material),
                "qty": int(p.qty),
                "quality": p.quality,
                "match_tick": int(p.match_tick),
                "order_id": p.order_id,
                "role": "buyer",
            }
        )
    for p in world.market_fob_pickups:
        if str(p.pickup_id) in seen or p.seller != party:
            continue
        out.append(
            {
                "pickup_id": p.pickup_id,
                "buyer": str(p.buyer),
                "seller": str(p.seller),
                "from_plot_id": str(p.from_plot_id),
                "material": str(p.material),
                "qty": int(p.qty),
                "quality": p.quality,
                "match_tick": int(p.match_tick),
                "order_id": p.order_id,
                "role": "buyer" if p.buyer == party else "seller",
            }
        )
    return out

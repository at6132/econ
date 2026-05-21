"""Physical settlement for order-book fills — DDP (seller ships) and FOB (buyer picks up)."""

from __future__ import annotations

from dataclasses import dataclass

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr, MatterOk, MatterResult
from realm.events.event_log import log_event
from realm.infrastructure.plot_logistics import add_party_plot_stock, owned_plot_ids_sorted
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
    world.market_fob_pickups.append(row)
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

    if terms == DELIVERY_FOB:
        return _append_fob_pickup(
            world,
            buyer=buyer,
            seller=seller,
            from_plot_id=from_plot,
            material=material,
            qty=qty,
            quality=quality,
            order_id=str(getattr(ask, "order_id", "")),
        )

    dest_raw = str(getattr(bid, "delivery_plot_id", "") or "") if bid is not None else ""
    dest_explicit = PlotId(dest_raw) if dest_raw else None
    dest = resolve_buyer_delivery_plot(world, buyer, explicit=dest_explicit)
    if dest is None:
        return MatterErr(reason="buyer has no plot to receive delivery")

    from realm.infrastructure.movement import dispatch_shipment

    ship = dispatch_shipment(
        world,
        seller,
        material,
        int(qty),
        from_plot,
        dest,
        consignee=buyer,
        escrowed_market=True,
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
        return MatterOk()

    # Cannot run DDP (no dock, fuel, cash, etc.) — fall back to FOB so trade still clears.
    log_event(
        world,
        "market_ddp_failed",
        f"DDP failed ({ship.get('reason', '?')}) — goods await FOB pickup at {from_plot}",
        seller=str(seller),
        buyer=str(buyer),
        material=str(material),
        qty=int(qty),
        reason=str(ship.get("reason", "")),
    )
    return _append_fob_pickup(
        world,
        buyer=buyer,
        seller=seller,
        from_plot_id=from_plot,
        material=material,
        qty=qty,
        quality=quality,
        order_id=str(getattr(ask, "order_id", "")),
    )


def pickup_fob(
    world: World,
    buyer: PartyId,
    pickup_id: str,
    *,
    to_plot_id: PlotId | None = None,
) -> dict:
    """Buyer arranges freight from the seller's listing plot (FOB)."""
    row: MarketFobPickup | None = None
    for p in world.market_fob_pickups:
        if p.pickup_id == pickup_id:
            row = p
            break
    if row is None:
        return {"ok": False, "reason": "pickup not found"}
    if row.buyer != buyer:
        return {"ok": False, "reason": "not your pickup"}
    dest = resolve_buyer_delivery_plot(world, buyer, explicit=to_plot_id)
    if dest is None:
        return {"ok": False, "reason": "no destination plot"}
    from realm.infrastructure.movement import dispatch_shipment

    ship = dispatch_shipment(
        world,
        buyer,
        row.material,
        int(row.qty),
        row.from_plot_id,
        dest,
        escrowed_market=True,
    )
    if not ship.get("ok"):
        return dict(ship)
    world.market_fob_pickups = [p for p in world.market_fob_pickups if p.pickup_id != pickup_id]
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


def fob_pickups_for_party(world: World, party: PartyId) -> list[dict]:
    out: list[dict] = []
    for p in world.market_fob_pickups:
        if p.buyer != party and p.seller != party:
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

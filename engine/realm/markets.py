"""Limit sell orders + market buy (Primitive 7b); P2P atomic trade (Primitive 7a)."""

from __future__ import annotations

from dataclasses import dataclass

from realm.ids import MaterialId, PartyId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World


@dataclass
class AskOrder:
    order_id: str
    party: PartyId
    material: MaterialId
    qty: int
    price_per_unit_cents: int


def _asks(world: World, material: MaterialId) -> list[AskOrder]:
    key = str(material)
    if key not in world.market_asks_by_material:
        world.market_asks_by_material[key] = []
    return world.market_asks_by_material[key]


def place_sell_order(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    price_per_unit_cents: int,
) -> dict:
    """List material for sale at a limit price (inventory removed until filled or cancelled)."""
    if qty <= 0 or price_per_unit_cents <= 0:
        return {"ok": False, "reason": "invalid qty or price"}
    if world.inventory.qty(party, material) < qty:
        return {"ok": False, "reason": "insufficient material"}
    rm = world.inventory.remove(party, material, qty)
    if isinstance(rm, MatterErr):
        return {"ok": False, "reason": rm.reason}
    world.next_order_seq += 1
    oid = f"ord-{world.next_order_seq}"
    _asks(world, material).append(
        AskOrder(
            order_id=oid,
            party=party,
            material=material,
            qty=qty,
            price_per_unit_cents=price_per_unit_cents,
        )
    )
    _asks(world, material).sort(key=lambda o: (o.price_per_unit_cents, o.order_id))
    return {"ok": True, "order_id": oid}


def cancel_sell_order(world: World, party: PartyId, order_id: str) -> dict:
    for key, lst in list(world.market_asks_by_material.items()):
        for i, o in enumerate(lst):
            if o.order_id == order_id:
                if o.party != party:
                    return {"ok": False, "reason": "not your order"}
                lst.pop(i)
                ad = world.inventory.add(party, o.material, o.qty)
                if isinstance(ad, MatterErr):
                    lst.insert(i, o)
                    return {"ok": False, "reason": ad.reason}
                if not lst:
                    del world.market_asks_by_material[key]
                return {"ok": True}
    return {"ok": False, "reason": "order not found"}


def market_buy(
    world: World, buyer: PartyId, material: MaterialId, max_qty: int
) -> dict:
    """
    Walk lowest-priced asks; pay sellers; deliver goods to buyer.

    Returns {ok: True, filled: int, spent_cents: int} | {ok: False, reason}.
    """
    if max_qty <= 0:
        return {"ok": False, "reason": "max_qty must be positive"}
    remaining = max_qty
    spent = 0
    asks = _asks(world, material)
    buyer_cash = party_cash_account(buyer)
    i = 0
    while i < len(asks) and remaining > 0:
        o = asks[i]
        fill = min(remaining, o.qty)
        cost = fill * o.price_per_unit_cents
        if world.ledger.balance(buyer_cash) < cost:
            break
        tr = world.ledger.transfer(
            debit=buyer_cash,
            credit=party_cash_account(o.party),
            amount_cents=cost,
        )
        if isinstance(tr, MoneyErr):
            break
        ad = world.inventory.add(buyer, material, fill)
        if isinstance(ad, MatterErr):
            world.ledger.transfer(
                debit=party_cash_account(o.party),
                credit=buyer_cash,
                amount_cents=cost,
            )
            break
        spent += cost
        remaining -= fill
        o.qty -= fill
        if o.qty <= 0:
            asks.pop(i)
            continue
        i += 1
    key = str(material)
    if key in world.market_asks_by_material and not world.market_asks_by_material[key]:
        del world.market_asks_by_material[key]
    if spent == 0 and max_qty > 0:
        return {"ok": False, "reason": "no liquidity or insufficient cash"}
    return {"ok": True, "filled": max_qty - remaining, "spent_cents": spent}


def p2p_trade(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    total_price_cents: int,
) -> dict:
    """Atomic: buyer pays seller total_price_cents; seller delivers qty material."""
    if qty <= 0 or total_price_cents < 0:
        return {"ok": False, "reason": "invalid trade"}
    if world.inventory.qty(seller, material) < qty:
        return {"ok": False, "reason": "seller lacks material"}
    bc = party_cash_account(buyer)
    sc = party_cash_account(seller)
    if world.ledger.balance(bc) < total_price_cents:
        return {"ok": False, "reason": "buyer insufficient cash"}
    pay = world.ledger.transfer(debit=bc, credit=sc, amount_cents=total_price_cents)
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}
    rm = world.inventory.remove(seller, material, qty)
    if isinstance(rm, MatterErr):
        world.ledger.transfer(debit=sc, credit=bc, amount_cents=total_price_cents)
        return {"ok": False, "reason": rm.reason}
    ad = world.inventory.add(buyer, material, qty)
    if isinstance(ad, MatterErr):
        world.inventory.add(seller, material, qty)
        world.ledger.transfer(debit=sc, credit=bc, amount_cents=total_price_cents)
        return {"ok": False, "reason": ad.reason}
    return {"ok": True}


def market_book_public(world: World) -> list[dict]:
    """Flatten asks for UI."""
    rows: list[dict] = []
    for mat_key, lst in sorted(world.market_asks_by_material.items()):
        for o in lst:
            rows.append(
                {
                    "order_id": o.order_id,
                    "party": str(o.party),
                    "material": mat_key,
                    "qty": o.qty,
                    "price_per_unit_cents": o.price_per_unit_cents,
                }
            )
    return rows


def transit_public(world: World) -> list[dict]:
    return [
        {
            "id": s.shipment_id,
            "party": str(s.party),
            "material": str(s.material),
            "qty": s.qty,
            "dest_plot_id": str(s.dest_plot_id),
            "arrive_tick": s.arrive_tick,
        }
        for s in world.in_transit
    ]

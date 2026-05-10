"""Limit order book: asks + bids (Primitive 7b); P2P (Primitive 7a).

Bids lock cash in ``system:market_escrow`` up to qty × limit price.
Crossing: incoming bid lifts resting asks at ask price; incoming ask lifts resting bids at bid limit.

**Matching:** at each price level, resting orders are **FIFO** by ``order_id`` (lexicographic order
matches creation order for ``ord-{seq}`` ids).
"""

from __future__ import annotations

from dataclasses import dataclass

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, market_escrow_account, party_cash_account
from realm.storage_caps import try_add_inventory
from realm.world import World


@dataclass
class AskOrder:
    order_id: str
    party: PartyId
    material: MaterialId
    qty: int
    price_per_unit_cents: int


@dataclass
class BidOrder:
    order_id: str
    party: PartyId
    material: MaterialId
    qty: int
    max_price_per_unit_cents: int
    escrow_cents: int


def _asks(world: World, material: MaterialId) -> list[AskOrder]:
    key = str(material)
    if key not in world.market_asks_by_material:
        world.market_asks_by_material[key] = []
    return world.market_asks_by_material[key]


def _bids(world: World, material: MaterialId) -> list[BidOrder]:
    key = str(material)
    if key not in world.market_bids_by_material:
        world.market_bids_by_material[key] = []
    return world.market_bids_by_material[key]


def _sort_asks(lst: list[AskOrder]) -> None:
    lst.sort(key=lambda o: (o.price_per_unit_cents, o.order_id))


def _sort_bids(lst: list[BidOrder]) -> None:
    lst.sort(key=lambda o: (-o.max_price_per_unit_cents, o.order_id))


def _clean_empty_book(world: World, material: MaterialId) -> None:
    k = str(material)
    if k in world.market_asks_by_material and not world.market_asks_by_material[k]:
        del world.market_asks_by_material[k]
    if k in world.market_bids_by_material and not world.market_bids_by_material[k]:
        del world.market_bids_by_material[k]


def _apply_cross_at_ask_price(world: World, bid: BidOrder, ask: AskOrder, fill: int, unit_px: int) -> bool:
    """Incoming bid hits resting ask: trade at ask price."""
    payment = fill * unit_px
    refund = fill * (bid.max_price_per_unit_cents - unit_px)
    escrow = market_escrow_account()
    buyer_c = party_cash_account(bid.party)
    seller_c = party_cash_account(ask.party)
    reserve = fill * bid.max_price_per_unit_cents
    if bid.escrow_cents < reserve:
        return False
    trp = world.ledger.transfer(debit=escrow, credit=seller_c, amount_cents=payment)
    if isinstance(trp, MoneyErr):
        return False
    if refund > 0:
        tru = world.ledger.transfer(debit=escrow, credit=buyer_c, amount_cents=refund)
        if isinstance(tru, MoneyErr):
            world.ledger.transfer(debit=seller_c, credit=escrow, amount_cents=payment)
            return False
    bid.escrow_cents -= reserve
    bid.qty -= fill
    ask.qty -= fill
    ad = try_add_inventory(world, bid.party, ask.material, fill)
    if isinstance(ad, MatterErr):
        bid.escrow_cents += reserve
        bid.qty += fill
        ask.qty += fill
        if refund > 0:
            world.ledger.transfer(debit=buyer_c, credit=escrow, amount_cents=refund)
        world.ledger.transfer(debit=seller_c, credit=escrow, amount_cents=payment)
        return False
    log_event(
        world,
        "market_match",
        f"{bid.party} bought {fill}×{ask.material} @ {unit_px}¢ (vs ask {ask.order_id})",
        buyer=str(bid.party),
        seller=str(ask.party),
        material=str(ask.material),
        qty=fill,
        price_per_unit_cents=unit_px,
    )
    return True


def _apply_cross_at_bid_price(world: World, bid: BidOrder, ask: AskOrder, fill: int, unit_px: int) -> bool:
    """Incoming ask hits resting bid: trade at bid limit."""
    payment = fill * unit_px
    escrow = market_escrow_account()
    buyer_c = party_cash_account(bid.party)
    seller_c = party_cash_account(ask.party)
    reserve = fill * bid.max_price_per_unit_cents
    if bid.escrow_cents < reserve:
        return False
    trp = world.ledger.transfer(debit=escrow, credit=seller_c, amount_cents=payment)
    if isinstance(trp, MoneyErr):
        return False
    bid.escrow_cents -= reserve
    bid.qty -= fill
    ask.qty -= fill
    ad = try_add_inventory(world, bid.party, ask.material, fill)
    if isinstance(ad, MatterErr):
        bid.escrow_cents += reserve
        bid.qty += fill
        ask.qty += fill
        world.ledger.transfer(debit=seller_c, credit=escrow, amount_cents=payment)
        return False
    log_event(
        world,
        "market_match",
        f"{ask.party} sold {fill}×{ask.material} @ {unit_px}¢ (vs bid {bid.order_id})",
        buyer=str(bid.party),
        seller=str(ask.party),
        material=str(ask.material),
        qty=fill,
        price_per_unit_cents=unit_px,
    )
    return True


def _cross_incoming_bid(world: World, bid: BidOrder) -> None:
    material = bid.material
    while bid.qty > 0:
        asks = _asks(world, material)
        if not asks or asks[0].price_per_unit_cents > bid.max_price_per_unit_cents:
            break
        ask = asks[0]
        fill = min(bid.qty, ask.qty)
        unit_px = ask.price_per_unit_cents
        if not _apply_cross_at_ask_price(world, bid, ask, fill, unit_px):
            break
        if ask.qty <= 0:
            asks.pop(0)
        _sort_asks(asks)
        if bid.qty <= 0:
            bids = _bids(world, material)
            for i, b in enumerate(bids):
                if b.order_id == bid.order_id:
                    bids.pop(i)
                    break
            _clean_empty_book(world, material)
            return
    _clean_empty_book(world, material)


def _cross_incoming_ask(world: World, ask: AskOrder) -> None:
    material = ask.material
    while ask.qty > 0:
        bids = _bids(world, material)
        if not bids or bids[0].max_price_per_unit_cents < ask.price_per_unit_cents:
            break
        bid = bids[0]
        fill = min(ask.qty, bid.qty)
        unit_px = bid.max_price_per_unit_cents
        if not _apply_cross_at_bid_price(world, bid, ask, fill, unit_px):
            break
        if bid.qty <= 0:
            bids.pop(0)
        _sort_bids(bids)
        if ask.qty <= 0:
            asks = _asks(world, material)
            for i, a in enumerate(asks):
                if a.order_id == ask.order_id:
                    asks.pop(i)
                    break
            _clean_empty_book(world, material)
            return
    _clean_empty_book(world, material)


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
    new_ask = AskOrder(
        order_id=oid,
        party=party,
        material=material,
        qty=qty,
        price_per_unit_cents=price_per_unit_cents,
    )
    lst = _asks(world, material)
    lst.append(new_ask)
    _sort_asks(lst)
    log_event(
        world,
        "market_list",
        f"{party} listed {qty}×{material} @ {price_per_unit_cents}¢/u ({oid})",
        party=str(party),
        material=str(material),
        qty=qty,
        price_per_unit_cents=price_per_unit_cents,
        order_id=oid,
    )
    _cross_incoming_ask(world, new_ask)
    return {"ok": True, "order_id": oid}


def cancel_sell_order(world: World, party: PartyId, order_id: str) -> dict:
    for key, lst in list(world.market_asks_by_material.items()):
        for i, o in enumerate(lst):
            if o.order_id == order_id:
                if o.party != party:
                    return {"ok": False, "reason": "not your order"}
                lst.pop(i)
                ad = try_add_inventory(world, party, o.material, o.qty)
                if isinstance(ad, MatterErr):
                    lst.insert(i, o)
                    return {"ok": False, "reason": ad.reason}
                if not lst:
                    del world.market_asks_by_material[key]
                log_event(
                    world,
                    "market_cancel",
                    f"{party} cancelled ask {order_id} ({o.qty}×{o.material})",
                    party=str(party),
                    order_id=order_id,
                    material=str(o.material),
                    qty=o.qty,
                )
                return {"ok": True}
    return {"ok": False, "reason": "order not found"}


def place_buy_order(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    max_price_per_unit_cents: int,
) -> dict:
    """Limit bid: lock qty × max price in market escrow; may immediately lift asks."""
    if qty <= 0 or max_price_per_unit_cents <= 0:
        return {"ok": False, "reason": "invalid qty or limit price"}
    escrow_need = qty * max_price_per_unit_cents
    buyer_c = party_cash_account(party)
    if world.ledger.balance(buyer_c) < escrow_need:
        return {"ok": False, "reason": "insufficient cash for bid"}
    tr = world.ledger.transfer(
        debit=buyer_c,
        credit=market_escrow_account(),
        amount_cents=escrow_need,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    world.next_order_seq += 1
    oid = f"ord-{world.next_order_seq}"
    bid = BidOrder(
        order_id=oid,
        party=party,
        material=material,
        qty=qty,
        max_price_per_unit_cents=max_price_per_unit_cents,
        escrow_cents=escrow_need,
    )
    bl = _bids(world, material)
    bl.append(bid)
    _sort_bids(bl)
    log_event(
        world,
        "market_bid",
        f"{party} bid {qty}×{material} up to {max_price_per_unit_cents}¢/u ({oid})",
        party=str(party),
        material=str(material),
        qty=qty,
        max_price_per_unit_cents=max_price_per_unit_cents,
        order_id=oid,
    )
    _cross_incoming_bid(world, bid)
    return {"ok": True, "order_id": oid}


def cancel_buy_order(world: World, party: PartyId, order_id: str) -> dict:
    for key, lst in list(world.market_bids_by_material.items()):
        for i, b in enumerate(lst):
            if b.order_id == order_id:
                if b.party != party:
                    return {"ok": False, "reason": "not your order"}
                refund = b.escrow_cents
                lst.pop(i)
                tr = world.ledger.transfer(
                    debit=market_escrow_account(),
                    credit=party_cash_account(party),
                    amount_cents=refund,
                )
                if isinstance(tr, MoneyErr):
                    lst.insert(i, b)
                    return {"ok": False, "reason": tr.reason}
                if not lst:
                    del world.market_bids_by_material[key]
                log_event(
                    world,
                    "market_cancel_bid",
                    f"{party} cancelled bid {order_id} (refund {refund}¢)",
                    party=str(party),
                    order_id=order_id,
                    material=str(b.material),
                    qty=b.qty,
                )
                return {"ok": True}
    return {"ok": False, "reason": "order not found"}


def market_buy(world: World, buyer: PartyId, material: MaterialId, max_qty: int) -> dict:
    """
    Aggressive buy: walk lowest-priced asks; pay sellers from buyer cash; deliver goods.
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
        ad = try_add_inventory(world, buyer, material, fill)
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
    filled = max_qty - remaining
    log_event(
        world,
        "market_buy",
        f"{buyer} bought {filled}×{material} for ${spent / 100:.2f}",
        buyer=str(buyer),
        material=str(material),
        filled=filled,
        spent_cents=spent,
    )
    return {"ok": True, "filled": filled, "spent_cents": spent}


def sell_into_bids(world: World, seller: PartyId, material: MaterialId, max_qty: int) -> dict:
    """
    Aggressive sell: walk highest bids; receive payment from bid escrow; deliver from seller inventory.
    """
    if max_qty <= 0:
        return {"ok": False, "reason": "max_qty must be positive"}
    remaining = max_qty
    received = 0
    seller_cash = party_cash_account(seller)
    escrow = market_escrow_account()
    while remaining > 0:
        bids = _bids(world, material)
        if not bids:
            break
        bid = bids[0]
        fill = min(remaining, bid.qty)
        unit_px = bid.max_price_per_unit_cents
        payment = fill * unit_px
        reserve = fill * bid.max_price_per_unit_cents
        if bid.escrow_cents < reserve:
            break
        if world.inventory.qty(seller, material) < fill:
            break
        tr = world.ledger.transfer(debit=escrow, credit=seller_cash, amount_cents=payment)
        if isinstance(tr, MoneyErr):
            break
        bid.escrow_cents -= reserve
        bid.qty -= fill
        rm = world.inventory.remove(seller, material, fill)
        if isinstance(rm, MatterErr):
            world.ledger.transfer(debit=seller_cash, credit=escrow, amount_cents=payment)
            bid.escrow_cents += reserve
            bid.qty += fill
            break
        ad = try_add_inventory(world, bid.party, material, fill)
        if isinstance(ad, MatterErr):
            world.inventory.add(seller, material, fill)
            world.ledger.transfer(debit=seller_cash, credit=escrow, amount_cents=payment)
            bid.escrow_cents += reserve
            bid.qty += fill
            break
        received += payment
        remaining -= fill
        log_event(
            world,
            "market_sell_fill",
            f"{seller} sold {fill}×{material} into book @ {unit_px}¢",
            seller=str(seller),
            buyer=str(bid.party),
            material=str(material),
            qty=fill,
            received_cents=payment,
        )
        if bid.qty <= 0:
            bids.pop(0)
        _sort_bids(bids)
    _clean_empty_book(world, material)
    if received == 0 and max_qty > 0:
        return {"ok": False, "reason": "no bids or insufficient inventory"}
    filled = max_qty - remaining
    return {"ok": True, "filled": filled, "received_cents": received}


_P2P_IDEMPOTENCY_MAX = 400


def _p2p_fingerprint(
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    total_price_cents: int,
) -> list[str | int]:
    return [str(seller), str(buyer), str(material), qty, total_price_cents]


def _trim_p2p_idempotency(world: World) -> None:
    while len(world.p2p_idempotency) > _P2P_IDEMPOTENCY_MAX:
        world.p2p_idempotency.pop(next(iter(world.p2p_idempotency)))


def _p2p_trade_execute(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    total_price_cents: int,
) -> dict:
    """Atomic: buyer pays seller total_price_cents; seller delivers qty material."""
    if qty <= 0 or total_price_cents < 0:
        return {"ok": False, "reason": "invalid trade", "code": "P2P_INVALID"}
    if world.inventory.qty(seller, material) < qty:
        return {"ok": False, "reason": "seller lacks material", "code": "P2P_SELLER_LACKS_MATERIAL"}
    bc = party_cash_account(buyer)
    sc = party_cash_account(seller)
    if world.ledger.balance(bc) < total_price_cents:
        return {"ok": False, "reason": "buyer insufficient cash", "code": "P2P_BUYER_INSUFFICIENT_CASH"}
    pay = world.ledger.transfer(debit=bc, credit=sc, amount_cents=total_price_cents)
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason, "code": "P2P_PAYMENT_FAILED"}
    rm = world.inventory.remove(seller, material, qty)
    if isinstance(rm, MatterErr):
        world.ledger.transfer(debit=sc, credit=bc, amount_cents=total_price_cents)
        return {"ok": False, "reason": rm.reason, "code": "P2P_SELLER_REMOVE_FAILED"}
    ad = try_add_inventory(world, buyer, material, qty)
    if isinstance(ad, MatterErr):
        world.inventory.add(seller, material, qty)
        world.ledger.transfer(debit=sc, credit=bc, amount_cents=total_price_cents)
        code = "P2P_BUYER_STORAGE_FULL" if ad.reason == "storage capacity exceeded" else "P2P_BUYER_ADD_FAILED"
        return {"ok": False, "reason": ad.reason, "code": code}
    log_event(
        world,
        "p2p_trade",
        f"P2P: {seller} sold {qty}×{material} to {buyer} for ${total_price_cents / 100:.2f}",
        seller=str(seller),
        buyer=str(buyer),
        material=str(material),
        qty=qty,
        total_price_cents=total_price_cents,
    )
    return {"ok": True, "code": "P2P_OK"}


def p2p_trade(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    total_price_cents: int,
    *,
    idempotency_key: str | None = None,
) -> dict:
    """
    P2P atomic trade. Optional ``idempotency_key``: same key + same parameters replays the stored
    outcome (success or failure) without double-settling.
    """
    fp = _p2p_fingerprint(seller, buyer, material, qty, total_price_cents)
    ikey = idempotency_key.strip() if idempotency_key else None
    if ikey:
        prior = world.p2p_idempotency.get(ikey)
        if prior is not None:
            if prior["fingerprint"] != fp:
                return {
                    "ok": False,
                    "reason": "idempotency key reused with different trade parameters",
                    "code": "P2P_IDEMPOTENCY_MISMATCH",
                }
            out = dict(prior["response"])
            out["idempotent_replay"] = True
            return out
    result = _p2p_trade_execute(world, seller, buyer, material, qty, total_price_cents)
    if ikey:
        _trim_p2p_idempotency(world)
        world.p2p_idempotency[ikey] = {
            "fingerprint": fp,
            "response": {k: v for k, v in result.items()},
        }
    return result


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
                    "side": "ask",
                }
            )
    return rows


def market_bids_public(world: World) -> list[dict]:
    """Flatten bids for UI."""
    rows: list[dict] = []
    for mat_key, lst in sorted(world.market_bids_by_material.items()):
        for b in lst:
            rows.append(
                {
                    "order_id": b.order_id,
                    "party": str(b.party),
                    "material": mat_key,
                    "qty": b.qty,
                    "max_price_per_unit_cents": b.max_price_per_unit_cents,
                    "side": "bid",
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

"""Limit order book: asks + bids (Primitive 7b); P2P (Primitive 7a).

Bids lock cash in ``system:market_escrow`` up to qty × limit price.
Crossing: incoming bid lifts resting asks at ask price; incoming ask lifts resting bids at bid limit.

**Matching:** at each price level, resting orders are **FIFO** by ``order_id`` (lexicographic order
matches creation order for ``ord-{seq}`` ids).

**Iceberg:** optional ``iceberg_display_qty`` (peak); hidden size refills the visible clip when depleted.
**Reputation gate:** optional ``min_counterparty_honored`` on bids/asks — no cross unless both parties
meet the other's minimum (0 = off).
"""

from __future__ import annotations

from dataclasses import dataclass

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, market_escrow_account, party_cash_account, system_reserve_account
from realm.social import bump_spot_exchange_honored
from realm.storage_caps import try_add_inventory
from realm.world import World

# Genesis clearinghouse: one-time seller registration per party+material before first resting ask.
MARKET_SELLER_REGISTRATION_CENTS = 2_000


def _market_seller_registration_key(party: PartyId, material: MaterialId) -> str:
    return f"{party}|{str(material)}"


def ensure_market_seller_registration(world: World, party: PartyId, material: MaterialId) -> dict:
    """
    In Genesis, first time a party lists a material on the exchange book they pay a registration fee.

    Returns {ok: True} | {ok: False, reason}.
    """
    if world.scenario_id != "genesis":
        return {"ok": True}
    key = _market_seller_registration_key(party, material)
    if key in world.market_seller_registered:
        return {"ok": True}
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < MARKET_SELLER_REGISTRATION_CENTS:
        return {"ok": False, "reason": "insufficient cash for exchange seller registration"}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=MARKET_SELLER_REGISTRATION_CENTS,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    world.market_seller_registered.add(key)
    log_event(
        world,
        "market_seller_register",
        f"{party} registered as seller of {material} on the exchange clearinghouse",
        party=str(party),
        material=str(material),
        fee_cents=MARKET_SELLER_REGISTRATION_CENTS,
    )
    return {"ok": True}


@dataclass
class AskOrder:
    order_id: str
    party: PartyId
    material: MaterialId
    qty: int
    price_per_unit_cents: int
    iceberg_peak: int = 0  # 0 = not iceberg; else max visible clip size
    iceberg_hidden_qty: int = 0  # units not yet shown at this price
    min_counterparty_honored: int = 0


@dataclass
class BidOrder:
    order_id: str
    party: PartyId
    material: MaterialId
    qty: int
    max_price_per_unit_cents: int
    escrow_cents: int
    iceberg_peak: int = 0
    iceberg_hidden_qty: int = 0
    min_counterparty_honored: int = 0


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


def best_resting_ask_cents(world: World, material: MaterialId) -> int | None:
    """Lowest limit sell price on the book, or None if no asks."""
    asks = _asks(world, material)
    _sort_asks(asks)
    if not asks:
        return None
    return int(asks[0].price_per_unit_cents)


def best_resting_bid_cents(world: World, material: MaterialId) -> int | None:
    """Highest limit buy price on the book, or None if no bids."""
    bids = _bids(world, material)
    _sort_bids(bids)
    if not bids:
        return None
    return int(bids[0].max_price_per_unit_cents)


def _clean_empty_book(world: World, material: MaterialId) -> None:
    k = str(material)
    if k in world.market_asks_by_material and not world.market_asks_by_material[k]:
        del world.market_asks_by_material[k]
    if k in world.market_bids_by_material and not world.market_bids_by_material[k]:
        del world.market_bids_by_material[k]


def _honored_count(world: World, party: PartyId) -> int:
    return int(world.reputation.get(str(party), {}).get("honored", 0))


def _rep_allows_match(bid: BidOrder, ask: AskOrder, world: World) -> bool:
    if _honored_count(world, ask.party) < bid.min_counterparty_honored:
        return False
    if _honored_count(world, bid.party) < ask.min_counterparty_honored:
        return False
    return True


def _ask_total_remaining(ask: AskOrder) -> int:
    return ask.qty + ask.iceberg_hidden_qty


def _bid_total_remaining(bid: BidOrder) -> int:
    return bid.qty + bid.iceberg_hidden_qty


def _replenish_iceberg_ask(ask: AskOrder) -> None:
    if ask.iceberg_peak <= 0:
        return
    if ask.qty > 0:
        return
    if ask.iceberg_hidden_qty <= 0:
        return
    rev = min(ask.iceberg_peak, ask.iceberg_hidden_qty)
    ask.qty = rev
    ask.iceberg_hidden_qty -= rev


def _replenish_iceberg_bid(bid: BidOrder) -> None:
    if bid.iceberg_peak <= 0:
        return
    if bid.qty > 0:
        return
    if bid.iceberg_hidden_qty <= 0:
        return
    rev = min(bid.iceberg_peak, bid.iceberg_hidden_qty)
    bid.qty = rev
    bid.iceberg_hidden_qty -= rev


def _apply_fill_to_ask(ask: AskOrder, fill: int) -> None:
    if ask.iceberg_peak <= 0:
        ask.qty -= fill
        return
    left = fill
    while left > 0:
        if ask.qty == 0:
            _replenish_iceberg_ask(ask)
        if ask.qty == 0:
            break
        step = min(left, ask.qty)
        ask.qty -= step
        left -= step
        _replenish_iceberg_ask(ask)


def _apply_fill_to_bid(bid: BidOrder, fill: int) -> None:
    if bid.iceberg_peak <= 0:
        bid.qty -= fill
        return
    left = fill
    while left > 0:
        if bid.qty == 0:
            _replenish_iceberg_bid(bid)
        if bid.qty == 0:
            break
        step = min(left, bid.qty)
        bid.qty -= step
        left -= step
        _replenish_iceberg_bid(bid)


def _ask_fully_done(ask: AskOrder) -> bool:
    return _ask_total_remaining(ask) <= 0


def _bid_fully_done(bid: BidOrder) -> bool:
    return _bid_total_remaining(bid) <= 0


def _first_ask_index_for_bid(world: World, bid: BidOrder, asks: list[AskOrder]) -> int | None:
    if not asks or asks[0].price_per_unit_cents > bid.max_price_per_unit_cents:
        return None
    best_px = asks[0].price_per_unit_cents
    for i, ask in enumerate(asks):
        if ask.price_per_unit_cents != best_px:
            break
        if _rep_allows_match(bid, ask, world):
            return i
    return None


def _first_bid_index_for_ask(world: World, ask: AskOrder, bids: list[BidOrder]) -> int | None:
    if not bids or bids[0].max_price_per_unit_cents < ask.price_per_unit_cents:
        return None
    best_px = bids[0].max_price_per_unit_cents
    for i, bid in enumerate(bids):
        if bid.max_price_per_unit_cents != best_px:
            break
        if _rep_allows_match(bid, ask, world):
            return i
    return None


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
    bid_snap = (bid.qty, bid.iceberg_hidden_qty, bid.escrow_cents)
    ask_snap = (ask.qty, ask.iceberg_hidden_qty)
    trp = world.ledger.transfer(debit=escrow, credit=seller_c, amount_cents=payment)
    if isinstance(trp, MoneyErr):
        return False
    if refund > 0:
        tru = world.ledger.transfer(debit=escrow, credit=buyer_c, amount_cents=refund)
        if isinstance(tru, MoneyErr):
            world.ledger.transfer(debit=seller_c, credit=escrow, amount_cents=payment)
            return False
    bid.escrow_cents -= reserve
    _apply_fill_to_bid(bid, fill)
    _apply_fill_to_ask(ask, fill)
    ad = try_add_inventory(world, bid.party, ask.material, fill)
    if isinstance(ad, MatterErr):
        bid.qty, bid.iceberg_hidden_qty, bid.escrow_cents = bid_snap
        ask.qty, ask.iceberg_hidden_qty = ask_snap
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
    bump_spot_exchange_honored(world, bid.party, ask.party)
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
    bid_snap = (bid.qty, bid.iceberg_hidden_qty, bid.escrow_cents)
    ask_snap = (ask.qty, ask.iceberg_hidden_qty)
    trp = world.ledger.transfer(debit=escrow, credit=seller_c, amount_cents=payment)
    if isinstance(trp, MoneyErr):
        return False
    bid.escrow_cents -= reserve
    _apply_fill_to_bid(bid, fill)
    _apply_fill_to_ask(ask, fill)
    ad = try_add_inventory(world, bid.party, ask.material, fill)
    if isinstance(ad, MatterErr):
        bid.qty, bid.iceberg_hidden_qty, bid.escrow_cents = bid_snap
        ask.qty, ask.iceberg_hidden_qty = ask_snap
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
    bump_spot_exchange_honored(world, bid.party, ask.party)
    return True


def _cross_incoming_bid(world: World, bid: BidOrder) -> None:
    material = bid.material
    while _bid_total_remaining(bid) > 0:
        asks = _asks(world, material)
        idx = _first_ask_index_for_bid(world, bid, asks)
        if idx is None:
            break
        ask = asks[idx]
        fill = min(bid.qty, ask.qty)
        unit_px = ask.price_per_unit_cents
        if not _apply_cross_at_ask_price(world, bid, ask, fill, unit_px):
            break
        _sort_asks(asks)
        if _ask_fully_done(ask):
            for j, o in enumerate(asks):
                if o.order_id == ask.order_id:
                    asks.pop(j)
                    break
        _sort_asks(asks)
        if _bid_fully_done(bid):
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
    while _ask_total_remaining(ask) > 0:
        bids = _bids(world, material)
        idx = _first_bid_index_for_ask(world, ask, bids)
        if idx is None:
            break
        bid = bids[idx]
        fill = min(ask.qty, bid.qty)
        unit_px = bid.max_price_per_unit_cents
        if not _apply_cross_at_bid_price(world, bid, ask, fill, unit_px):
            break
        _sort_bids(bids)
        if _bid_fully_done(bid):
            for j, b in enumerate(bids):
                if b.order_id == bid.order_id:
                    bids.pop(j)
                    break
        _sort_bids(bids)
        if _ask_fully_done(ask):
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
    *,
    iceberg_display_qty: int | None = None,
    min_counterparty_honored: int = 0,
) -> dict:
    """List material for sale at a limit price (inventory removed until filled or cancelled)."""
    if qty <= 0 or price_per_unit_cents <= 0:
        return {"ok": False, "reason": "invalid qty or price"}
    if min_counterparty_honored < 0:
        return {"ok": False, "reason": "min_counterparty_honored must be non-negative"}
    if iceberg_display_qty is not None and (
        iceberg_display_qty < 1 or iceberg_display_qty >= qty
    ):
        return {"ok": False, "reason": "iceberg_display_qty must be >= 1 and < qty"}
    reg = ensure_market_seller_registration(world, party, material)
    if not reg.get("ok"):
        return dict(reg)
    if world.inventory.qty(party, material) < qty:
        return {"ok": False, "reason": "insufficient material"}
    rm = world.inventory.remove(party, material, qty)
    if isinstance(rm, MatterErr):
        return {"ok": False, "reason": rm.reason}
    ice_peak = 0
    ice_hid = 0
    vis = qty
    if iceberg_display_qty is not None:
        ice_peak = iceberg_display_qty
        vis = ice_peak
        ice_hid = qty - vis
    world.next_order_seq += 1
    oid = f"ord-{world.next_order_seq}"
    new_ask = AskOrder(
        order_id=oid,
        party=party,
        material=material,
        qty=vis,
        price_per_unit_cents=price_per_unit_cents,
        iceberg_peak=ice_peak,
        iceberg_hidden_qty=ice_hid,
        min_counterparty_honored=min_counterparty_honored,
    )
    lst = _asks(world, material)
    lst.append(new_ask)
    _sort_asks(lst)
    log_event(
        world,
        "market_list",
        f"{party} listed {qty}×{material} @ {price_per_unit_cents}¢/u ({oid})"
        + (f" [iceberg peak {ice_peak}]" if ice_peak > 0 else ""),
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
                total_back = o.qty + o.iceberg_hidden_qty
                ad = try_add_inventory(world, party, o.material, total_back)
                if isinstance(ad, MatterErr):
                    lst.insert(i, o)
                    return {"ok": False, "reason": ad.reason}
                if not lst:
                    del world.market_asks_by_material[key]
                log_event(
                    world,
                    "market_cancel",
                    f"{party} cancelled ask {order_id} ({total_back}×{o.material})",
                    party=str(party),
                    order_id=order_id,
                    material=str(o.material),
                    qty=total_back,
                )
                return {"ok": True}
    return {"ok": False, "reason": "order not found"}


def cancel_party_asks_for_material(world: World, party: PartyId, material: MaterialId) -> int:
    """Cancel every resting sell order ``party`` has for ``material``. Returns count removed."""
    key = str(material)
    lst = world.market_asks_by_material.get(key, [])
    ids = [o.order_id for o in lst if o.party == party]
    n = 0
    for oid in ids:
        r = cancel_sell_order(world, party, oid)
        if r.get("ok"):
            n += 1
    return n


def place_buy_order(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    max_price_per_unit_cents: int,
    *,
    iceberg_display_qty: int | None = None,
    min_counterparty_honored: int = 0,
) -> dict:
    """Limit bid: lock qty × max price in market escrow; may immediately lift asks."""
    if qty <= 0 or max_price_per_unit_cents <= 0:
        return {"ok": False, "reason": "invalid qty or limit price"}
    if min_counterparty_honored < 0:
        return {"ok": False, "reason": "min_counterparty_honored must be non-negative"}
    escrow_need = qty * max_price_per_unit_cents
    buyer_c = party_cash_account(party)
    if world.ledger.balance(buyer_c) < escrow_need:
        return {"ok": False, "reason": "insufficient cash for bid"}
    ice_peak = 0
    ice_hid = 0
    vis = qty
    if iceberg_display_qty is not None:
        if iceberg_display_qty < 1 or iceberg_display_qty >= qty:
            return {"ok": False, "reason": "iceberg_display_qty must be >= 1 and < qty"}
        ice_peak = iceberg_display_qty
        vis = ice_peak
        ice_hid = qty - vis
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
        qty=vis,
        max_price_per_unit_cents=max_price_per_unit_cents,
        escrow_cents=escrow_need,
        iceberg_peak=ice_peak,
        iceberg_hidden_qty=ice_hid,
        min_counterparty_honored=min_counterparty_honored,
    )
    bl = _bids(world, material)
    bl.append(bid)
    _sort_bids(bl)
    log_event(
        world,
        "market_bid",
        f"{party} bid {qty}×{material} up to {max_price_per_unit_cents}¢/u ({oid})"
        + (f" [iceberg peak {ice_peak}]" if ice_peak > 0 else ""),
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


def cancel_party_bids_for_material(world: World, party: PartyId, material: MaterialId) -> int:
    """Cancel every resting buy order ``party`` has for ``material``. Returns count removed."""
    key = str(material)
    lst = world.market_bids_by_material.get(key, [])
    ids = [b.order_id for b in lst if b.party == party]
    n = 0
    for oid in ids:
        r = cancel_buy_order(world, party, oid)
        if r.get("ok"):
            n += 1
    return n


def cancel_all_party_resting_orders(world: World, party: PartyId) -> None:
    """Cancel all resting asks and bids for ``party`` (e.g. bankruptcy / retirement cleanup)."""
    for key in list(world.market_asks_by_material.keys()):
        cancel_party_asks_for_material(world, party, MaterialId(key))
    for key in list(world.market_bids_by_material.keys()):
        cancel_party_bids_for_material(world, party, MaterialId(key))


def market_buy(
    world: World,
    buyer: PartyId,
    material: MaterialId,
    max_qty: int,
    *,
    min_seller_honored: int = 0,
) -> dict:
    """
    Aggressive buy: walk asks in ascending price order; pay sellers from buyer cash; deliver goods.

    Skips asks whose ``min_counterparty_honored`` the buyer cannot satisfy, then continues to
    higher-priced fillable clips (so rep-gated cheap listings do not block the whole book).
    """
    if max_qty <= 0:
        return {"ok": False, "reason": "max_qty must be positive"}
    if min_seller_honored < 0:
        return {"ok": False, "reason": "min_seller_honored must be non-negative"}
    remaining = max_qty
    spent = 0
    buyer_cash = party_cash_account(buyer)
    seller_parties: set[str] = set()
    first_seller_str: str | None = None
    while remaining > 0:
        asks = _asks(world, material)
        _sort_asks(asks)
        if not asks:
            break
        idx = None
        for j, o in enumerate(asks):
            if (
                _honored_count(world, o.party) >= min_seller_honored
                and _honored_count(world, buyer) >= o.min_counterparty_honored
            ):
                idx = j
                break
        if idx is None:
            break
        o = asks[idx]
        fill = min(remaining, o.qty)
        cost = fill * o.price_per_unit_cents
        if world.ledger.balance(buyer_cash) < cost:
            break
        ask_snap = (o.qty, o.iceberg_hidden_qty)
        tr = world.ledger.transfer(
            debit=buyer_cash,
            credit=party_cash_account(o.party),
            amount_cents=cost,
        )
        if isinstance(tr, MoneyErr):
            break
        _apply_fill_to_ask(o, fill)
        ad = try_add_inventory(world, buyer, material, fill)
        if isinstance(ad, MatterErr):
            o.qty, o.iceberg_hidden_qty = ask_snap
            world.ledger.transfer(
                debit=party_cash_account(o.party),
                credit=buyer_cash,
                amount_cents=cost,
            )
            break
        spent += cost
        remaining -= fill
        seller_parties.add(str(o.party))
        if first_seller_str is None:
            first_seller_str = str(o.party)
        bump_spot_exchange_honored(world, buyer, o.party)
        if _ask_fully_done(o):
            asks.pop(idx)
        _sort_asks(asks)
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
        party=str(buyer),
        material=str(material),
        filled=filled,
        spent_cents=spent,
        seller=first_seller_str or "",
        sellers=",".join(sorted(seller_parties)) if seller_parties else "",
    )
    if world.scenario_id == "genesis" and filled > 0:
        from realm.genesis_feed_hooks import note_genesis_hub_market_buy

        note_genesis_hub_market_buy(
            world,
            buyer=buyer,
            material=material,
            filled=int(filled),
            sellers_csv=",".join(sorted(seller_parties)) if seller_parties else "",
        )
    return {"ok": True, "filled": filled, "spent_cents": spent}


def sell_into_bids(
    world: World,
    seller: PartyId,
    material: MaterialId,
    max_qty: int,
    *,
    min_buyer_honored: int = 0,
) -> dict:
    """
    Aggressive sell: walk bids in descending price order; receive payment from bid escrow.

    Skips bids whose ``min_counterparty_honored`` the seller cannot satisfy, then continues to
    lower-priced fillable clips.
    """
    if max_qty <= 0:
        return {"ok": False, "reason": "max_qty must be positive"}
    if min_buyer_honored < 0:
        return {"ok": False, "reason": "min_buyer_honored must be non-negative"}
    if world.inventory.qty(seller, material) < 1:
        return {"ok": False, "reason": "insufficient material"}
    reg = ensure_market_seller_registration(world, seller, material)
    if not reg.get("ok"):
        return dict(reg)
    remaining = max_qty
    received = 0
    seller_cash = party_cash_account(seller)
    escrow = market_escrow_account()
    while remaining > 0:
        bids = _bids(world, material)
        _sort_bids(bids)
        if not bids:
            break
        idx = None
        for j, b in enumerate(bids):
            if (
                _honored_count(world, b.party) >= min_buyer_honored
                and _honored_count(world, seller) >= b.min_counterparty_honored
            ):
                idx = j
                break
        if idx is None:
            break
        bid = bids[idx]
        fill = min(remaining, bid.qty)
        unit_px = bid.max_price_per_unit_cents
        payment = fill * unit_px
        reserve = fill * bid.max_price_per_unit_cents
        if bid.escrow_cents < reserve:
            break
        if world.inventory.qty(seller, material) < fill:
            break
        bid_snap = (bid.qty, bid.iceberg_hidden_qty, bid.escrow_cents)
        tr = world.ledger.transfer(debit=escrow, credit=seller_cash, amount_cents=payment)
        if isinstance(tr, MoneyErr):
            break
        bid.escrow_cents -= reserve
        _apply_fill_to_bid(bid, fill)
        rm = world.inventory.remove(seller, material, fill)
        if isinstance(rm, MatterErr):
            bid.qty, bid.iceberg_hidden_qty, bid.escrow_cents = bid_snap
            world.ledger.transfer(debit=seller_cash, credit=escrow, amount_cents=payment)
            break
        ad = try_add_inventory(world, bid.party, material, fill)
        if isinstance(ad, MatterErr):
            world.inventory.add(seller, material, fill)
            bid.qty, bid.iceberg_hidden_qty, bid.escrow_cents = bid_snap
            world.ledger.transfer(debit=seller_cash, credit=escrow, amount_cents=payment)
            break
        received += payment
        remaining -= fill
        bump_spot_exchange_honored(world, bid.party, seller)
        log_event(
            world,
            "market_sell_fill",
            f"{seller} sold {fill}×{material} into book @ {unit_px}¢",
            seller=str(seller),
            party=str(seller),
            buyer=str(bid.party),
            material=str(material),
            qty=fill,
            received_cents=payment,
        )
        if _bid_fully_done(bid):
            bids.pop(idx)
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
    bump_spot_exchange_honored(world, buyer, seller)
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
            total = _ask_total_remaining(o)
            rows.append(
                {
                    "order_id": o.order_id,
                    "party": str(o.party),
                    "material": mat_key,
                    "qty": o.qty,
                    "qty_total_remaining": total,
                    "price_per_unit_cents": o.price_per_unit_cents,
                    "side": "ask",
                    "iceberg_peak": o.iceberg_peak,
                    "iceberg_hidden_qty": o.iceberg_hidden_qty,
                    "min_counterparty_honored": o.min_counterparty_honored,
                }
            )
    return rows


def market_bids_public(world: World) -> list[dict]:
    """Flatten bids for UI."""
    rows: list[dict] = []
    for mat_key, lst in sorted(world.market_bids_by_material.items()):
        for b in lst:
            total = _bid_total_remaining(b)
            rows.append(
                {
                    "order_id": b.order_id,
                    "party": str(b.party),
                    "material": mat_key,
                    "qty": b.qty,
                    "qty_total_remaining": total,
                    "max_price_per_unit_cents": b.max_price_per_unit_cents,
                    "side": "bid",
                    "iceberg_peak": b.iceberg_peak,
                    "iceberg_hidden_qty": b.iceberg_hidden_qty,
                    "min_counterparty_honored": b.min_counterparty_honored,
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

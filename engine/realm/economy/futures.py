"""Futures market — public delivery commitments with escrowed deposits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, futures_escrow_account, party_cash_account
from realm.world import World

MIN_FUTURES_CURVE_MATCHES: Final[int] = 3


@dataclass
class FuturesOrder:
    order_id: str
    side: str
    poster: PartyId
    material: MaterialId
    qty: int
    price_per_unit_cents: int
    delivery_tick: int
    deposit_cents: int
    status: str
    matched_with: str | None = None
    posted_at_tick: int = 0
    match_price_cents: int | None = None


def post_futures_order(
    world: World,
    poster: PartyId,
    side: str,
    material: MaterialId,
    qty: int,
    price_per_unit_cents: int,
    delivery_tick: int,
) -> dict[str, Any]:
    if side not in ("sell", "buy"):
        return {"ok": False, "reason": "side must be 'sell' or 'buy'"}
    if int(delivery_tick) <= int(world.tick):
        return {"ok": False, "reason": "delivery_tick must be in the future"}
    if qty <= 0 or price_per_unit_cents <= 0:
        return {"ok": False, "reason": "qty and price must be positive"}
    if poster not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    notional = int(qty) * int(price_per_unit_cents)
    deposit = max(1, notional // 10)
    pc = party_cash_account(poster)
    if world.ledger.balance(pc) < deposit:
        return {"ok": False, "reason": f"need {deposit}¢ deposit (10% of notional)"}
    esc = futures_escrow_account()
    tr = world.ledger.transfer(debit=pc, credit=esc, amount_cents=deposit)
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    seq = int(world.scenario_state.get("next_futures_seq", 1))
    world.scenario_state["next_futures_seq"] = seq + 1
    oid = f"fut_{seq:08d}"
    order = FuturesOrder(
        order_id=oid,
        side=str(side),
        poster=poster,
        material=material,
        qty=int(qty),
        price_per_unit_cents=int(price_per_unit_cents),
        delivery_tick=int(delivery_tick),
        deposit_cents=int(deposit),
        status="open",
        posted_at_tick=int(world.tick),
    )
    world.futures_orders.append(order)
    log_event(
        world,
        "futures_order_posted",
        f"{poster} posted {side} futures {oid}",
        order_id=oid,
        side=side,
        material=str(material),
        qty=int(qty),
        price=int(price_per_unit_cents),
        delivery_tick=int(delivery_tick),
    )
    return {"ok": True, "order_id": oid, "deposit_cents": deposit}


def cancel_futures_order(world: World, party: PartyId, order_id: str) -> dict[str, Any]:
    for o in world.futures_orders:
        if o.order_id != order_id:
            continue
        if o.poster != party:
            return {"ok": False, "reason": "not your order"}
        if o.status != "open":
            return {"ok": False, "reason": "order not cancellable"}
        esc = futures_escrow_account()
        pc = party_cash_account(party)
        tr = world.ledger.transfer(debit=esc, credit=pc, amount_cents=int(o.deposit_cents))
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        o.status = "cancelled"
        return {"ok": True}
    return {"ok": False, "reason": "order not found"}


def tick_futures_matching(world: World) -> None:
    from collections import defaultdict

    pairs: dict[tuple[str, int], dict[str, list[FuturesOrder]]] = defaultdict(
        lambda: {"sells": [], "buys": []}
    )
    for o in world.futures_orders:
        if o.status != "open":
            continue
        key = (str(o.material), int(o.delivery_tick))
        if o.side == "sell":
            pairs[key]["sells"].append(o)
        elif o.side == "buy":
            pairs[key]["buys"].append(o)
    for (_mat, _dtick), sides in pairs.items():
        sells = sorted(sides["sells"], key=lambda x: (x.price_per_unit_cents, x.order_id))
        buys = sorted(sides["buys"], key=lambda x: (-x.price_per_unit_cents, x.order_id))
        for sell, buy in zip(sells, buys):
            if buy.price_per_unit_cents < sell.price_per_unit_cents:
                break
            fill_price = (sell.price_per_unit_cents + buy.price_per_unit_cents) // 2
            sell.status = "matched"
            buy.status = "matched"
            sell.matched_with = buy.order_id
            buy.matched_with = sell.order_id
            sell.match_price_cents = fill_price
            buy.match_price_cents = fill_price
            log_event(
                world,
                "futures_matched",
                f"Futures matched {sell.order_id}↔{buy.order_id} @ {fill_price}¢/u",
                sell_order=sell.order_id,
                buy_order=buy.order_id,
                fill_price=fill_price,
            )
    _maybe_emit_futures_curve_feed(world)


def _maybe_emit_futures_curve_feed(world: World) -> None:
    by_mat: dict[str, list[tuple[int, int]]] = {}
    for o in world.futures_orders:
        if o.status != "matched" or o.side != "sell":
            continue
        mp = int(o.match_price_cents or o.price_per_unit_cents)
        by_mat.setdefault(str(o.material), []).append((int(o.delivery_tick), mp))
    last_key = "futures_curve_last_tick"
    last = int(world.scenario_state.get(last_key, -1))
    if int(world.tick) == last:
        return
    for mat, rows in by_mat.items():
        uniq_ticks = {t for t, _ in rows}
        if len(uniq_ticks) < MIN_FUTURES_CURVE_MATCHES:
            continue
        rows.sort(key=lambda r: r[0])
        parts = [f"{p}¢@{t}t" for t, p in rows[:5]]
        log_event(
            world,
            "world_feed",
            f"{mat} futures curve: " + ", ".join(parts),
            feed_source="futures_curve",
            material=mat,
        )
        world.scenario_state[last_key] = int(world.tick)
        return


def _futures_default(
    world: World,
    sell: FuturesOrder,
    buy: FuturesOrder,
    *,
    defaulter: PartyId,
    counterparty: PartyId,
    reason: str,
) -> None:
    esc = futures_escrow_account()
    seller_pc = party_cash_account(sell.poster)
    buyer_pc = party_cash_account(buy.poster)
    if defaulter == sell.poster:
        world.ledger.transfer(
            debit=esc, credit=buyer_pc, amount_cents=int(sell.deposit_cents)
        )
        world.ledger.transfer(
            debit=esc, credit=buyer_pc, amount_cents=int(buy.deposit_cents)
        )
    else:
        world.ledger.transfer(
            debit=esc, credit=seller_pc, amount_cents=int(buy.deposit_cents)
        )
        world.ledger.transfer(
            debit=esc, credit=seller_pc, amount_cents=int(sell.deposit_cents)
        )
    sell.status = "defaulted"
    buy.status = "defaulted"
    br = world.reputation.setdefault(str(defaulter), {"honored": 0, "breached": 0})
    br["breached"] = int(br.get("breached", 0)) + 1
    log_event(
        world,
        "futures_defaulted",
        f"Futures default {sell.order_id}: {reason}",
        reason=reason,
        defaulter=str(defaulter),
        counterparty=str(counterparty),
    )


def tick_futures_settlement(world: World) -> None:
    t = int(world.tick)
    for sell in list(world.futures_orders):
        if sell.status != "matched" or sell.side != "sell":
            continue
        if int(sell.delivery_tick) > t:
            continue
        buy = next((o for o in world.futures_orders if o.order_id == sell.matched_with), None)
        if buy is None or buy.side != "buy":
            sell.status = "defaulted"
            continue
        seller = sell.poster
        buyer = buy.poster
        material = sell.material
        qty = int(sell.qty)
        price = int(sell.match_price_cents or sell.price_per_unit_cents)
        payment = qty * price
        if world.inventory.qty(seller, material) < qty:
            _futures_default(
                world,
                sell,
                buy,
                defaulter=seller,
                counterparty=buyer,
                reason="insufficient material",
            )
            continue
        bc = party_cash_account(buyer)
        if world.ledger.balance(bc) < payment:
            _futures_default(
                world,
                sell,
                buy,
                defaulter=buyer,
                counterparty=seller,
                reason="insufficient cash",
            )
            continue
        sc = party_cash_account(seller)
        trp = world.ledger.transfer(debit=bc, credit=sc, amount_cents=payment)
        if isinstance(trp, MoneyErr):
            _futures_default(
                world,
                sell,
                buy,
                defaulter=buyer,
                counterparty=seller,
                reason="insufficient cash",
            )
            continue
        mv = world.inventory.transfer(
            material=material, qty=qty, from_party=seller, to_party=buyer
        )
        if isinstance(mv, MatterErr):
            _futures_default(
                world,
                sell,
                buy,
                defaulter=seller,
                counterparty=buyer,
                reason="insufficient material",
            )
            continue
        esc = futures_escrow_account()
        world.ledger.transfer(
            debit=esc, credit=sc, amount_cents=int(sell.deposit_cents)
        )
        world.ledger.transfer(
            debit=esc, credit=bc, amount_cents=int(buy.deposit_cents)
        )
        sell.status = "filled"
        buy.status = "filled"
        for p in (seller, buyer):
            r = world.reputation.setdefault(str(p), {"honored": 0, "breached": 0})
            r["honored"] = int(r.get("honored", 0)) + 1
        log_event(
            world,
            "futures_settled",
            f"Futures settled {qty}×{material} {seller}→{buyer} @ {price}¢/u",
            material=str(material),
            qty=qty,
            price=price,
        )


def tick_futures_pipeline(world: World) -> None:
    tick_futures_matching(world)
    tick_futures_settlement(world)

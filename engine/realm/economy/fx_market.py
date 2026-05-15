"""Cross-currency exchange orders (material currencies + base cents)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, fx_escrow_account, party_cash_account
from realm.materials import CURRENCY_MATERIAL_IDS
from realm.world import World

FX_ESCROW_PARTY: PartyId = PartyId("fx_escrow_vault")
TICKS_PER_7_GAME_DAYS: int = 7 * 1440


@dataclass
class FXOrder:
    order_id: str
    poster: PartyId
    sell_material: str
    sell_qty: int
    buy_material: str
    buy_qty_min: int
    posted_at_tick: int
    status: str
    expires_at_tick: int
    filled_sell_qty: int = 0
    filled_buy_qty: int = 0


def _ensure_fx_party(world: World) -> None:
    world.parties.add(FX_ESCROW_PARTY)


def _is_allowed_currency(world: World, mat_s: str) -> bool:
    if mat_s == "base_cents":
        return True
    mid = MaterialId(mat_s)
    return mid in CURRENCY_MATERIAL_IDS


def post_fx_order(
    world: World,
    poster: PartyId,
    sell_material: str,
    sell_qty: int,
    buy_material: str,
    buy_qty_min: int,
) -> dict[str, Any]:
    if sell_qty <= 0 or buy_qty_min <= 0:
        return {"ok": False, "reason": "quantities must be positive"}
    if not _is_allowed_currency(world, sell_material) or not _is_allowed_currency(world, buy_material):
        return {"ok": False, "reason": "material is not an allowed FX leg"}
    if sell_material == buy_material:
        return {"ok": False, "reason": "cannot trade a currency for itself"}
    if poster not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    _ensure_fx_party(world)
    esc = fx_escrow_account()
    if sell_material == "base_cents":
        pc = party_cash_account(poster)
        if world.ledger.balance(pc) < int(sell_qty):
            return {"ok": False, "reason": "insufficient base currency"}
        tr = world.ledger.transfer(debit=pc, credit=esc, amount_cents=int(sell_qty))
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
    else:
        mat = MaterialId(sell_material)
        mv = world.inventory.transfer(
            material=mat, qty=int(sell_qty), from_party=poster, to_party=FX_ESCROW_PARTY
        )
        if isinstance(mv, MatterErr):
            return {"ok": False, "reason": mv.reason}
    seq = int(world.scenario_state.get("next_fx_seq", 1))
    world.scenario_state["next_fx_seq"] = seq + 1
    oid = f"fx_{seq:08d}"
    exp = int(world.tick) + TICKS_PER_7_GAME_DAYS
    world.fx_orders.append(
        FXOrder(
            order_id=oid,
            poster=poster,
            sell_material=str(sell_material),
            sell_qty=int(sell_qty),
            buy_material=str(buy_material),
            buy_qty_min=int(buy_qty_min),
            posted_at_tick=int(world.tick),
            status="open",
            expires_at_tick=exp,
        )
    )
    return {"ok": True, "order_id": oid}


def cancel_fx_order(world: World, party: PartyId, order_id: str) -> dict[str, Any]:
    for o in world.fx_orders:
        if o.order_id != order_id or o.poster != party or o.status != "open":
            continue
        _fx_release_escrow(world, o)
        o.status = "cancelled"
        return {"ok": True}
    return {"ok": False, "reason": "order not found"}


def _fx_release_escrow(world: World, o: FXOrder) -> None:
    esc = fx_escrow_account()
    if o.sell_material == "base_cents":
        world.ledger.transfer(
            debit=esc, credit=party_cash_account(o.poster), amount_cents=int(o.sell_qty)
        )
    else:
        world.inventory.transfer(
            material=MaterialId(o.sell_material),
            qty=int(o.sell_qty),
            from_party=FX_ESCROW_PARTY,
            to_party=o.poster,
        )


def _fx_expire_orders(world: World) -> None:
    t = int(world.tick)
    for o in world.fx_orders:
        if o.status != "open":
            continue
        if t <= int(o.expires_at_tick):
            continue
        _fx_release_escrow(world, o)
        o.status = "cancelled"


def tick_fx_matching(world: World) -> None:
    _fx_expire_orders(world)
    open_orders = [o for o in world.fx_orders if o.status == "open"]
    for i, a in enumerate(open_orders):
        for b in open_orders[i + 1 :]:
            if b.status != "open":
                continue
            if not (
                a.sell_material == b.buy_material
                and a.buy_material == b.sell_material
            ):
                continue
            rate_a = float(a.sell_qty) / max(1, float(a.buy_qty_min))
            rate_b = float(b.sell_qty) / max(1, float(b.buy_qty_min))
            if rate_a * rate_b < 1.0:
                continue
            _fx_execute_pair(world, a, b)
            return


def _fx_execute_pair(world: World, a: FXOrder, b: FXOrder) -> None:
    """Settle a complementary pair: each poster receives the other's escrowed sell leg."""
    _ensure_fx_party(world)
    qty = min(int(a.sell_qty), int(b.buy_qty_min), int(b.sell_qty), int(a.buy_qty_min))
    if qty <= 0:
        return
    esc = fx_escrow_account()
    if a.sell_material == "base_cents":
        world.ledger.transfer(debit=esc, credit=party_cash_account(b.poster), amount_cents=qty)
    else:
        world.inventory.transfer(
            material=MaterialId(a.sell_material),
            qty=qty,
            from_party=FX_ESCROW_PARTY,
            to_party=b.poster,
        )
    if b.sell_material == "base_cents":
        world.ledger.transfer(debit=esc, credit=party_cash_account(a.poster), amount_cents=qty)
    else:
        world.inventory.transfer(
            material=MaterialId(b.sell_material),
            qty=qty,
            from_party=FX_ESCROW_PARTY,
            to_party=a.poster,
        )
    a.status = "filled"
    b.status = "filled"
    a.filled_sell_qty = qty
    b.filled_sell_qty = qty
    log_event(
        world,
        "fx_matched",
        f"FX {a.order_id} matched {b.order_id} qty={qty}",
        order_a=a.order_id,
        order_b=b.order_id,
    )


def tick_fx_rates(world: World) -> None:
    if int(world.tick) <= 0 or int(world.tick) % 1440 != 0:
        return
    recent = [
        o
        for o in world.fx_orders
        if o.status == "filled" and int(world.tick) - int(o.posted_at_tick) <= 1440
    ]
    rates: dict[str, list[float]] = {}
    for o in recent:
        pair = f"{o.sell_material}/{o.buy_material}"
        implied = float(o.sell_qty) / max(1, float(o.buy_qty_min))
        rates.setdefault(pair, []).append(implied)
    board: dict[str, float] = {}
    for k, rs in rates.items():
        board[k] = sum(rs) / len(rs)
    world.scenario_state["fx_rate_board"] = board
    hist = world.scenario_state.setdefault("fx_rate_history", [])
    if not isinstance(hist, list):
        hist = []
        world.scenario_state["fx_rate_history"] = hist
    hist.append({"tick": int(world.tick), "board": copy.deepcopy(board)})
    world.scenario_state["fx_rate_history"] = hist[-400:]
    if board:
        bits = [f"{k}={v:.3f}" for k, v in sorted(board.items())[:8]]
        world.world_feed_log.append(
            {
                "tick": int(world.tick),
                "kind": "world_feed",
                "message": "Today's exchange rates: " + "; ".join(bits) + ".",
            }
        )


def tick_fx_pipeline(world: World) -> None:
    tick_fx_matching(world)
    tick_fx_rates(world)

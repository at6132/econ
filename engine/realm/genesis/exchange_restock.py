"""Genesis exchange emergency restock — last-resort supply after prolonged market absence."""
from __future__ import annotations

from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.economy.markets import place_sell_order
from realm.economy.pricing import exchange_ask_cents
from realm.events.event_log import log_event
from realm.world import World

_RESTOCK_INTERVAL_TICKS: int = 1440
_EMERGENCY_ABSENCE_DAYS: int = 45
_EMERGENCY_PRICE_MULT: float = 4.0
_RESTOCK_MAX_RESTOCKS: int = 1
_EMERGENCY_QTY: int = 10

# Survival staples + worn hand tools (settlers cannot produce without picks/spades).
_RESTOCK_MATERIALS: list[tuple[str, int, int]] = [
    ("grain", _EMERGENCY_QTY, 500),
    ("coal", _EMERGENCY_QTY, 500),
]
_TOOL_RESTOCK_MATERIALS: list[tuple[str, int, int]] = [
    ("mining_pick", 3, 6),
    ("spade", 3, 6),
    ("pick_axe", 2, 4),
]
_TOOL_ABSENCE_DAYS: int = 1


def tick_genesis_exchange_restock(world: World) -> None:
    """Last-resort emergency supply — fires once per material after 45 days of total absence."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) % _RESTOCK_INTERVAL_TICKS != 0:
        return
    ex = PartyId("genesis_exchange")
    if ex not in world.parties:
        return
    restock_state: dict[str, int] = world.scenario_state.setdefault(
        "genesis_exchange_restocks", {}
    )

    for mat_s, relist_qty, inv_add_qty in _RESTOCK_MATERIALS:
        mid = MaterialId(mat_s)
        restocks = int(restock_state.get(mat_s, 0))
        if restocks >= _RESTOCK_MAX_RESTOCKS:
            continue

        all_asks = world.market_asks_by_material.get(mat_s, [])
        absence_key = f"{mat_s}_absent_since"
        if all_asks:
            restock_state.pop(absence_key, None)
            continue

        if absence_key not in restock_state:
            restock_state[absence_key] = int(world.tick)
            continue
        absent_ticks = int(world.tick) - int(restock_state[absence_key])
        if absent_ticks < _EMERGENCY_ABSENCE_DAYS * 1440:
            continue

        base = exchange_ask_cents(mid)
        emergency_price = int(base * _EMERGENCY_PRICE_MULT)
        inv_now = world.inventory.qty(ex, mid)
        need = max(0, inv_add_qty - inv_now)
        if need > 0:
            cost = need * emergency_price
            tr = world.ledger.transfer(
                debit=system_reserve_account(),
                credit=party_cash_account(ex),
                amount_cents=cost,
            )
            if isinstance(tr, MoneyErr):
                continue
            ad = world.inventory.add(ex, mid, need)
            if isinstance(ad, MatterErr):
                world.ledger.transfer(
                    debit=party_cash_account(ex),
                    credit=system_reserve_account(),
                    amount_cents=cost,
                )
                continue
        res = place_sell_order(world, ex, mid, relist_qty, emergency_price)
        if res.get("ok"):
            restock_state[mat_s] = restocks + 1
            restock_state.pop(absence_key, None)
            log_event(
                world,
                "world_feed",
                f"EMERGENCY: exchange released {relist_qty}×{mat_s} @ {emergency_price/100:.2f}¢ "
                f"— market has been dry for {absent_ticks // 1440} days.",
                feed_source="exchange_emergency",
                material=mat_s,
                price_cents=emergency_price,
            )

    for mat_s, relist_qty, inv_add_qty in _TOOL_RESTOCK_MATERIALS:
        mid = MaterialId(mat_s)
        restocks = int(restock_state.get(f"tool_{mat_s}", 0))
        if restocks >= 3:
            continue
        all_asks = world.market_asks_by_material.get(mat_s, [])
        absence_key = f"tool_{mat_s}_absent_since"
        if all_asks:
            restock_state.pop(absence_key, None)
            continue
        if absence_key not in restock_state:
            restock_state[absence_key] = int(world.tick)
            continue
        absent_ticks = int(world.tick) - int(restock_state[absence_key])
        if absent_ticks < _TOOL_ABSENCE_DAYS * 1440:
            continue
        base = exchange_ask_cents(mid)
        emergency_price = max(4, int(base * 2.5))
        inv_now = world.inventory.qty(ex, mid)
        need = max(0, inv_add_qty - inv_now)
        if need > 0:
            cost = need * emergency_price
            tr = world.ledger.transfer(
                debit=system_reserve_account(),
                credit=party_cash_account(ex),
                amount_cents=cost,
            )
            if isinstance(tr, MoneyErr):
                continue
            ad = world.inventory.add(ex, mid, need)
            if isinstance(ad, MatterErr):
                world.ledger.transfer(
                    debit=party_cash_account(ex),
                    credit=system_reserve_account(),
                    amount_cents=cost,
                )
                continue
        res = place_sell_order(world, ex, mid, relist_qty, emergency_price)
        if res.get("ok"):
            restock_state[f"tool_{mat_s}"] = restocks + 1
            restock_state.pop(absence_key, None)

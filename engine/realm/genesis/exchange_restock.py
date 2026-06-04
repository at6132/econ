"""Genesis exchange adaptive restock — re-lists depleted staples at escalating prices.

Creates visible price discovery: grain $1.61 → $1.85 → $2.13 as it depletes,
signalling to settlers that farming is profitable. Caps at 8 restocks per material
so prices eventually stabilise once settler supply matures.
"""
from __future__ import annotations

from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.economy.markets import place_sell_order
from realm.economy.pricing import exchange_ask_cents
from realm.events.event_log import log_event
from realm.world import World

_RESTOCK_INTERVAL_TICKS: int = 1440
_RESTOCK_PRICE_BUMP_PCT: float = 0.15
_RESTOCK_MAX_RESTOCKS: int = 8

# (material_id, relist_qty, inv_add_qty)
_RESTOCK_MATERIALS: list[tuple[str, int, int]] = [
    ("grain", 40, 60_000),
    ("coal", 50, 500_000),
    ("timber", 50, 200_000),
    ("lumber", 30, 100_000),
    ("brick", 40, 100_000),
    ("stone", 40, 100_000),
]


def tick_genesis_exchange_restock(world: World) -> None:
    """Re-list depleted genesis_exchange staples at escalating prices (price discovery)."""
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
        asks = world.market_asks_by_material.get(mat_s, [])
        ex_asks = [a for a in asks if a.party == ex]
        if ex_asks:
            continue

        restocks = int(restock_state.get(mat_s, 0))
        if restocks >= _RESTOCK_MAX_RESTOCKS:
            continue

        base = exchange_ask_cents(mid)
        new_price = max(base, int(base * (1.0 + _RESTOCK_PRICE_BUMP_PCT) ** restocks))

        inv_now = world.inventory.qty(ex, mid)
        need = max(0, inv_add_qty - inv_now)
        if need > 0:
            cost = need * new_price
            reserve = system_reserve_account()
            ex_acct = party_cash_account(ex)
            tr = world.ledger.transfer(debit=reserve, credit=ex_acct, amount_cents=cost)
            if isinstance(tr, MoneyErr):
                continue
            ad = world.inventory.add(ex, mid, need)
            if isinstance(ad, MatterErr):
                world.ledger.transfer(debit=ex_acct, credit=reserve, amount_cents=cost)
                continue

        res = place_sell_order(world, ex, mid, relist_qty, new_price)
        if res.get("ok"):
            restock_state[mat_s] = restocks + 1
            log_event(
                world,
                "world_feed",
                f"Exchange restocked {relist_qty}×{mat_s} @ {new_price/100:.2f}¢/u "
                f"(restock #{restocks + 1}/{_RESTOCK_MAX_RESTOCKS}) — "
                f"supply pressure building.",
                feed_source="exchange_restock",
                material=mat_s,
                price_cents=new_price,
                restock_num=restocks + 1,
            )

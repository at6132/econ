"""Genesis clearinghouse — backstop market-maker (quotes spreaded asks, withdraws when settlers supply)."""

from __future__ import annotations

from realm.genesis_pricing import (
    EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK,
    exchange_ask_cents,
)
from realm.ids import MaterialId, PartyId
from realm.markets import place_sell_order
from realm.world import World

_GENESIS_EXCHANGE = PartyId("genesis_exchange")

# Target backstop depth per material when no real seller is on the book.
# Price is derived from the fair-value table in ``genesis_pricing`` (+ spread).
_STAPLES: tuple[tuple[MaterialId, int], ...] = (
    (MaterialId("coal"), 48),
    (MaterialId("electricity"), 56),
    (MaterialId("grain"), 48),
    (MaterialId("timber"), 36),
    (MaterialId("lumber"), 500),
    (MaterialId("brick"), 500),
    (MaterialId("stone"), 500),
    (MaterialId("pick_axe"), 200),
    (MaterialId("mining_pick"), 200),
    (MaterialId("spade"), 200),
    (MaterialId("hand_saw"), 100),
)


def tick_genesis_exchange_quoting(world: World) -> None:
    """
    Top-of-tick liquidity backstop.

    The clearinghouse only restocks when **non-exchange** resting ask depth is
    below ``EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK`` — i.e. settlers/players are
    not already supplying. When real producers have the book covered, the
    exchange withdraws and lets settler clips clear first (price-time priority
    naturally favours their lower ask).
    """
    if world.scenario_id != "genesis" or _GENESIS_EXCHANGE not in world.parties:
        return
    for mid, target_units in _STAPLES:
        key = str(mid)
        asks = world.market_asks_by_material.get(key, [])
        ex_on_book = 0
        non_ex_on_book = 0
        for o in asks:
            visible = int(o.qty) + int(o.iceberg_hidden_qty)
            if o.party == _GENESIS_EXCHANGE:
                ex_on_book += visible
            else:
                non_ex_on_book += visible
        if non_ex_on_book >= EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK:
            continue
        need = max(0, target_units - ex_on_book)
        if need <= 0:
            continue
        inv = world.inventory.qty(_GENESIS_EXCHANGE, mid)
        if inv <= 0:
            continue
        clip = min(need, inv, 90)
        if clip > 0:
            place_sell_order(world, _GENESIS_EXCHANGE, mid, clip, exchange_ask_cents(mid))

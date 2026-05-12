"""Genesis cold-start exchange — keep staple asks on the book (relist from unlisted inventory)."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import place_sell_order
from realm.world import World

_GENESIS_EXCHANGE = PartyId("genesis_exchange")

# Target visible depth per material (genesis_exchange clips only; avoids one mega-order).
_STAPLE_TARGETS: tuple[tuple[MaterialId, int, int], ...] = (
    (MaterialId("coal"), 62, 72),
    (MaterialId("electricity"), 52, 80),
    (MaterialId("grain"), 128, 64),
    (MaterialId("timber"), 96, 48),
)


def tick_genesis_exchange_quoting(world: World) -> None:
    """
    Restock limit sells from ``genesis_exchange`` inventory when the book is thin.

    Bootstrap seeds a **large** unlisted pool; this tick keeps liquidity so hubs and
    settlers can ``market_buy`` inputs without a dead book.
    """
    if world.scenario_id != "genesis" or _GENESIS_EXCHANGE not in world.parties:
        return
    for mid, price_cents, target_units in _STAPLE_TARGETS:
        key = str(mid)
        asks = world.market_asks_by_material.get(key, [])
        ex_on_book = sum(
            int(o.qty) + int(o.iceberg_hidden_qty)
            for o in asks
            if o.party == _GENESIS_EXCHANGE and str(o.material) == str(mid)
        )
        need = max(0, target_units - ex_on_book)
        if need <= 0:
            continue
        inv = world.inventory.qty(_GENESIS_EXCHANGE, mid)
        if inv <= 0:
            continue
        clip = min(need, inv, 90)
        if clip > 0:
            place_sell_order(world, _GENESIS_EXCHANGE, mid, clip, price_cents)

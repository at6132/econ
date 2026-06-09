"""NPC procurement — tenders and restocking driven by economic reasoning."""

from __future__ import annotations

from typing import Final

from realm.agents.economic_reasoning import evaluate_staple_purchase
from realm.contracts.tenders import (
    TENDER_BID_WINDOW_TICKS,
    TENDER_DURATION_CYCLES,
    TENDER_INTERVAL_PER_CYCLE_TICKS,
    list_open_tenders,
    post_tender,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.economy.markets import market_buy, place_buy_order
from realm.world import World

_TICKS_PER_GAME_WEEK: Final[int] = 7 * TICKS_PER_GAME_DAY

_PROCUREMENT_BASKET: Final[tuple[tuple[MaterialId, int, int], ...]] = (
    (MaterialId("coal"), 12, 20),
    (MaterialId("grain"), 10, 18),
    (MaterialId("timber"), 8, 16),
    (MaterialId("lumber"), 6, 14),
    (MaterialId("iron_ore"), 6, 12),
    (MaterialId("flour"), 6, 12),
    (MaterialId("bread"), 8, 14),
    (MaterialId("fish"), 6, 12),
)

_STOREKEEPER_PARTY: Final[PartyId] = PartyId("genesis_storekeeper")
_TARGET_STOCK_BY_MATERIAL: Final[dict[str, int]] = {
    str(m): qty for m, qty, _ in _PROCUREMENT_BASKET
}


def _procurement_buyers(world: World) -> list[PartyId]:
    out: list[PartyId] = []
    try:
        from realm.genesis.consolidator import CONSOLIDATOR_PARTY_ID

        if CONSOLIDATOR_PARTY_ID in world.parties:
            out.append(CONSOLIDATOR_PARTY_ID)
    except ImportError:
        pass
    if _STOREKEEPER_PARTY in world.parties:
        out.append(_STOREKEEPER_PARTY)
    for p in sorted(world.parties, key=str):
        s = str(p)
        if s.startswith("pop_hub") and p not in out:
            out.append(p)
    return out


def _open_tender_for_buyer_material(
    world: World, buyer: PartyId, material: MaterialId
) -> bool:
    for t in list_open_tenders(world):
        if str(t.get("posted_by")) == str(buyer) and str(t.get("material")) == str(material):
            return True
    return False


def _restock_party_material(world: World, buyer: PartyId, material: MaterialId) -> None:
    target = int(_TARGET_STOCK_BY_MATERIAL.get(str(material), 8))
    have = int(world.inventory.qty(buyer, material))
    decision = evaluate_staple_purchase(
        world,
        buyer,
        material,
        target_stock=target,
        current_stock=have,
    )
    if decision is None:
        return
    ceiling, qty = decision
    place_buy_order(world, buyer, material, qty, max(4, ceiling - 2))
    market_buy(world, buyer, material, qty, max_price_per_unit_cents=ceiling)


def tick_npc_tender_posting(world: World) -> None:
    """Periodic: anchor buyers post supply tenders when they can fund them."""
    if int(world.tick) <= 0 or int(world.tick) % (5 * TICKS_PER_GAME_DAY) != 0:
        return

    buyers = _procurement_buyers(world)
    if not buyers:
        return

    slot = int(world.tick) // _TICKS_PER_GAME_WEEK
    for i, (material, qty_per_cycle, duration_cycles) in enumerate(_PROCUREMENT_BASKET):
        buyer = buyers[(slot + i) % len(buyers)]
        if _open_tender_for_buyer_material(world, buyer, material):
            continue
        cash = world.ledger.balance(party_cash_account(buyer))
        if cash < 10_000:
            continue
        post_tender(
            world,
            posted_by=buyer,
            material=material,
            qty_per_cycle=qty_per_cycle,
            interval_ticks=TENDER_INTERVAL_PER_CYCLE_TICKS,
            duration_cycles=duration_cycles,
            bid_window_ticks=TENDER_BID_WINDOW_TICKS,
        )


def _ensure_tool_asks_on_exchange(world: World) -> None:
    """List hand tools when market depth is thin — any producer may need them."""
    ex = PartyId("genesis_exchange")
    if ex not in world.parties:
        return
    from realm.economy.markets import place_sell_order
    from realm.economy.pricing import exchange_ask_cents

    need_tools = False
    for party in world.parties:
        if not str(party).startswith("settler_"):
            continue
        if world.inventory.qty(party, MaterialId("mining_pick")) < 1:
            need_tools = True
            break
        if world.inventory.qty(party, MaterialId("spade")) < 1:
            need_tools = True
            break
    if not need_tools:
        return
    for mat_s in ("mining_pick", "spade", "pick_axe"):
        mid = MaterialId(mat_s)
        if world.market_asks_by_material.get(str(mid)):
            continue
        have = int(world.inventory.qty(ex, mid))
        if have < 1:
            continue
        px = max(4, int(exchange_ask_cents(mid, world=world)))
        place_sell_order(world, ex, mid, min(3, have), px)


def _collect_npc_fob_pickups(world: World, buyers: list[PartyId]) -> None:
    """Anchor buyers collect FOB lots they paid for (cross-island coal from inland miners)."""
    from realm.economy.market_delivery import _fob_ids_for_buyer, pickup_fob

    buyer_set = set(buyers)
    try:
        from realm.genesis.energy import NPC_ENERGY_IDS

        buyer_set.update(NPC_ENERGY_IDS)
    except ImportError:
        pass
    for buyer in buyer_set:
        for pid in list(_fob_ids_for_buyer(world, buyer)):
            pickup_fob(world, buyer, pid)


def tick_genesis_standing_demand(world: World) -> None:
    """Daily: buyers restock staples when oracle + inventory say it is worth it."""
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return

    buyers = _procurement_buyers(world)
    if not buyers:
        return

    _ensure_tool_asks_on_exchange(world)

    day = int(world.tick) // TICKS_PER_GAME_DAY
    for i, (material, _qty_per_cycle, _dur) in enumerate(_PROCUREMENT_BASKET):
        buyer = buyers[(day + i) % len(buyers)]
        _restock_party_material(world, buyer, material)

    _collect_npc_fob_pickups(world, buyers)

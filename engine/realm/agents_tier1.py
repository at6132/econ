"""Tier 1 behavioral agents — cheap rule-based NPCs (doc 06 / Phase 1)."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import market_buy, place_sell_order
from realm.world import World


def tick_tier1_agents(world: World) -> None:
    """NPC loops: consume staples, buy outputs, refresh commodity supply."""
    _grain_consumer(world)
    _lumber_buyer(world)
    _timber_merchant(world)


def _grain_consumer(world: World) -> None:
    if world.tick % 5 != 0:
        return
    buyer = PartyId("t1_consumer")
    if buyer not in world.parties:
        return
    market_buy(world, buyer, MaterialId("grain"), 1)


def _lumber_buyer(world: World) -> None:
    if world.tick % 7 != 0:
        return
    buyer = PartyId("t1_lumber_buyer")
    if buyer not in world.parties:
        return
    market_buy(world, buyer, MaterialId("lumber"), 1)


def _timber_merchant(world: World) -> None:
    """Restock cheap timber asks when holding inventory (keeps sawmill chain liquid)."""
    if world.tick == 0 or world.tick % 14 != 0:
        return
    party = PartyId("t1_timber_merchant")
    if party not in world.parties:
        return
    if world.inventory.qty(party, MaterialId("timber")) >= 2:
        place_sell_order(world, party, MaterialId("timber"), 2, 72)

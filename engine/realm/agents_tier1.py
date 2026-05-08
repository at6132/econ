"""Tier 1 behavioral agents — cheap rule-based NPCs (doc 06 / Phase 1)."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import market_buy
from realm.world import World


def tick_tier1_agents(world: World) -> None:
    """Periodic market buy from seed consumer (needs listed asks)."""
    if world.tick % 5 != 0:
        return
    buyer = PartyId("t1_consumer")
    if buyer not in world.parties:
        return
    market_buy(world, buyer, MaterialId("grain"), 1)

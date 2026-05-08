"""Tier 1 behavioral agents — six cheap NPC loops (Phase 1 / doc 06)."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import market_buy, place_sell_order
from realm.world import World


def tick_tier1_agents(world: World) -> None:
    """Archetypes: staple consumer, output buyer, timber relister, coal & clay suppliers, power buyer."""
    _grain_consumer(world)
    _lumber_buyer(world)
    _timber_merchant(world)
    _coal_vendor(world)
    _clay_vendor(world)
    _electricity_buyer(world)


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
    """Restock timber asks when holding inventory (keeps sawmill chain liquid)."""
    if world.tick == 0 or world.tick % 14 != 0:
        return
    party = PartyId("t1_timber_merchant")
    if party not in world.parties:
        return
    if world.inventory.qty(party, MaterialId("timber")) >= 2:
        place_sell_order(world, party, MaterialId("timber"), 2, 72)


def _coal_vendor(world: World) -> None:
    if world.tick == 0 or world.tick % 18 != 0:
        return
    party = PartyId("t1_coal_vendor")
    if party not in world.parties:
        return
    if world.inventory.qty(party, MaterialId("coal")) >= 1:
        place_sell_order(world, party, MaterialId("coal"), 1, 40)


def _clay_vendor(world: World) -> None:
    if world.tick == 0 or world.tick % 22 != 0:
        return
    party = PartyId("t1_clay_vendor")
    if party not in world.parties:
        return
    if world.inventory.qty(party, MaterialId("clay")) >= 1:
        place_sell_order(world, party, MaterialId("clay"), 1, 52)


def _electricity_buyer(world: World) -> None:
    if world.tick % 9 != 0:
        return
    party = PartyId("t1_electricity_buyer")
    if party not in world.parties:
        return
    market_buy(world, party, MaterialId("electricity"), 2)

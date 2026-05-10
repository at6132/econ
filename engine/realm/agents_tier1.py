"""Tier 1 behavioral agents — six cheap NPC loops (Phase 1 / doc 06).

Archetype summary (all respect ``world.tick``; no wall-clock):

- **t1_consumer** — every 5 ticks: ``market_buy`` grain (1u).
- **t1_lumber_buyer** — every 7 ticks: ``market_buy`` lumber (1u).
- **t1_timber_merchant** — tick 0 or every 14 ticks: if holding ≥2 timber, ``place_sell_order`` (2u @ 72¢).
- **t1_coal_vendor** — tick 0 or every 18 ticks: if holding ≥1 coal, ``place_sell_order`` (1u @ 40¢).
- **t1_clay_vendor** — tick 0 or every 22 ticks: if holding ≥1 clay, ``place_sell_order`` (1u @ 52¢).
- **t1_electricity_buyer** — every 9 ticks: ``market_buy`` electricity (2u).

Failures are silent (engine returns ``ok: false``); agents do not retry within the same tick.
Ledger total should stay constant across ticks (see ``test_tier1_agent_ticks_conserve_total_cents``).
"""

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

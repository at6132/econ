"""Tick loop entry — advances simulation time (Law 2)."""

from __future__ import annotations

from realm.agents_tier1 import tick_tier1_agents
from realm.actions import tick_stub_employment
from realm.market_history import record_market_snapshot
from realm.movement import deliver_transit
from realm.production import tick_production
from realm.spoilage import tick_material_spoilage
from realm.social import tick_supply_contract_breaches
from realm.world import World


def advance_tick(world: World) -> None:
    """One simulation step: transit → production → agents → clock."""
    deliver_transit(world)
    tick_production(world)
    tick_material_spoilage(world)
    tick_stub_employment(world)
    tick_tier1_agents(world)
    world.tick += 1
    tick_supply_contract_breaches(world)
    record_market_snapshot(world)

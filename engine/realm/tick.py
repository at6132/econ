"""Tick loop entry — advances simulation time (Law 2)."""

from __future__ import annotations

from realm.agents_tier1 import tick_tier1_agents
from realm.agents_tier2 import tick_tier2_agents
from realm.agents_tier3 import tick_tier3_llm_agents
from realm.actions import tick_stub_employment
from realm.decay import tick_building_decay
from realm.market_history import record_market_snapshot
from realm.movement import deliver_transit
from realm.production import tick_production
from realm.spoilage import tick_material_spoilage
from realm.social import tick_supply_contract_breaches
from realm.contract_stubs import tick_phase2_financial_contracts
from realm.world import World


def advance_tick(world: World) -> None:
    """One simulation step: transit → production → agents → clock."""
    deliver_transit(world)
    tick_building_decay(world)
    tick_production(world)
    tick_material_spoilage(world)
    tick_stub_employment(world)
    tick_tier1_agents(world)
    tick_tier2_agents(world)
    tick_tier3_llm_agents(world)
    world.tick += 1
    tick_supply_contract_breaches(world)
    tick_phase2_financial_contracts(world)
    record_market_snapshot(world)

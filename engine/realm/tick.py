"""Tick loop entry — advances simulation time (Law 2)."""

from __future__ import annotations

from realm.agents_genesis import tick_genesis_agents
from realm.assay import tick_assay_jobs
from realm.deep_survey import tick_deep_survey_jobs
from realm.genesis_digest import tick_genesis_world_feed
from realm.genesis_feed_hooks import tick_genesis_feed_tick_scan
from realm.agents_tier1 import tick_tier1_agents
from realm.agents_tier2 import tick_tier2_agents
from realm.agents_tier3 import tick_tier3_llm_agents
from realm.actions import tick_stub_employment
from realm.decay import tick_building_decay, tick_building_maintenance
from realm.market_history import record_market_snapshot
from realm.movement import deliver_transit
from realm.production import tick_production
from realm.spoilage import tick_material_spoilage
from realm.social import tick_supply_contract_breaches
from realm.contract_stubs import tick_phase2_financial_contracts
from realm.energy import ensure_powered_plots_fresh
from realm.world import World


def advance_tick(world: World) -> None:
    """One simulation step: transit → production → agents → clock."""
    deliver_transit(world)
    tick_building_decay(world)
    tick_building_maintenance(world)
    ensure_powered_plots_fresh(world)
    tick_production(world)
    tick_material_spoilage(world)
    tick_stub_employment(world)
    tick_assay_jobs(world)
    tick_deep_survey_jobs(world)
    if world.scenario_id == "genesis":
        tick_genesis_agents(world)
    else:
        tick_tier1_agents(world)
        tick_tier2_agents(world)
    tick_tier3_llm_agents(world)
    world.tick += 1
    if world.scenario_id == "genesis":
        tick_genesis_feed_tick_scan(world)
        tick_genesis_world_feed(world)
    tick_supply_contract_breaches(world)
    tick_phase2_financial_contracts(world)
    record_market_snapshot(world)

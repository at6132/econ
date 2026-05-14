"""Tick loop entry — advances simulation time (Law 2)."""

from __future__ import annotations

from realm.agents.genesis import tick_genesis_agents
from realm.assay import tick_assay_jobs
from realm.deep_survey import tick_deep_survey_jobs
from realm.genesis_digest import tick_genesis_world_feed
from realm.genesis_feed_hooks import tick_genesis_feed_tick_scan
from realm.agents.tier1 import tick_tier1_agents
from realm.agents.tier2 import tick_tier2_agents
from realm.agents.tier3 import tick_tier3_llm_agents
from realm.actions import tick_stub_employment
from realm.production.decay import tick_building_decay, tick_building_maintenance
from realm.economy.market_history import record_market_snapshot
from realm.movement import deliver_transit
from realm.events.price_alerts import tick_price_alerts
from realm.production import tick_production, tick_production_auto_restart
from realm.production.spoilage import tick_material_spoilage
from realm.social import tick_supply_contract_breaches
from realm.contract_stubs import tick_phase2_financial_contracts
from realm.energy import ensure_powered_plots_fresh
from realm.genesis_bank import tick_bank_loans
from realm.genesis_road_builders import tick_frontier_roads
from realm.genesis_margaux_sprint5 import (
    tick_margaux_sprint5_beats,
    update_margaux_player_profile,
)
from realm.employment import tick_job_market, tick_laborer_wages
from realm.laborers import tick_laborer_births, tick_laborers
from realm.events.sprint4_feed import tick_sprint4_feed
from realm.stores import tick_laborer_spending
from realm.world import World


def advance_tick(world: World) -> None:
    """One simulation step: transit → production → agents → clock."""
    deliver_transit(world)
    tick_building_decay(world)
    tick_building_maintenance(world)
    ensure_powered_plots_fresh(world)
    tick_production(world)
    tick_production_auto_restart(world)
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
    tick_bank_loans(world)
    if world.scenario_id == "genesis":
        tick_frontier_roads(world)
        tick_laborers(world)
        tick_job_market(world)
        tick_laborer_wages(world)
        tick_laborer_spending(world)
        tick_laborer_births(world)
    record_market_snapshot(world)
    tick_price_alerts(world)
    if world.scenario_id == "genesis":
        tick_sprint4_feed(world)
        update_margaux_player_profile(world)
        tick_margaux_sprint5_beats(world)

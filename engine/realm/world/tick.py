"""Tick loop entry — advances simulation time (Law 2)."""

from __future__ import annotations

from realm.agents.genesis import tick_genesis_agents
from realm.actions.assay_actions import tick_assay_jobs
from realm.research.patents import (
    tick_era_advancement,
    tick_patent_licensing,
    tick_research_competition,
)
from realm.research.research_lab import tick_research_progress
from realm.actions.deep_survey_actions import tick_deep_survey_jobs
from realm.genesis.digest import tick_genesis_world_feed
from realm.genesis.feed_hooks import tick_genesis_feed_tick_scan
from realm.agents.tier1 import tick_tier1_agents
from realm.agents.tier2 import tick_tier2_agents
from realm.agents.tier3 import tick_tier3_llm_agents
from realm.actions import tick_stub_employment
from realm.production.decay import tick_building_decay, tick_building_maintenance
from realm.economy.inter_island import tick_inter_island_buy_orders
from realm.infrastructure.roads import tick_road_decay
from realm.economy.market_events import tick_market_events
from realm.economy.market_history import record_market_snapshot
from realm.infrastructure.movement import deliver_transit
from realm.events.price_alerts import tick_price_alerts
from realm.events.seasons import tick_seasons
from realm.events.world_events import tick_world_events
from realm.production import tick_production, tick_production_auto_restart
from realm.production.spoilage import tick_material_spoilage
from realm.contracts.social import tick_liens, tick_supply_contract_breaches
from realm.genesis.home_builders import tick_home_builders
from realm.population.towns import tick_assign_homeless_laborers
from realm.contracts.stubs import tick_phase2_financial_contracts
from realm.genesis.bank import tick_bank_loans
from realm.genesis.road_builders import tick_frontier_roads
from realm.genesis.margaux_sprint5 import (
    tick_margaux_sprint5_beats,
    update_margaux_player_profile,
)
from realm.population.employment import (
    tick_job_market,
    tick_laborer_wages,
    tick_settler_job_postings,
)
from realm.population.laborers import tick_laborer_births, tick_labor_pool_replenishment, tick_laborers
from realm.population.laborer_lifecycle import (
    tick_laborer_health,
    tick_laborer_reproduction,
    tick_laborer_savings,
    tick_laborer_skills,
)
from realm.events.sprint4_feed import tick_sprint4_feed
from realm.population.stores import tick_laborer_spending, tick_store_restock
from realm.actions.construction_actions import tick_construction_firms, tick_construction_orders
from realm.economy.business_viability import tick_business_viability
from realm.population.nascent_settlements import tick_nascent_settlements
from realm.world import World
from realm.world.real_estate import tick_npc_plot_demand


def advance_tick(world: World) -> None:
    """One simulation step: transit → production → agents → clock."""
    deliver_transit(world)
    from realm.economy.asset_depreciation import (
        tick_asset_depreciation,
        tick_placed_building_activation,
    )

    tick_placed_building_activation(world)
    tick_asset_depreciation(world)
    tick_building_decay(world)
    tick_building_maintenance(world)
    tick_road_decay(world)
    tick_production(world)
    tick_production_auto_restart(world)
    if world.scenario_id == "genesis":
        tick_laborer_skills(world)
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
    tick_npc_plot_demand(world)
    world.tick += 1
    if int(world.tick) % 1440 == 0:
        from realm.agents.market_oracle import get_oracle
        from realm.economy.holding_costs import tick_holding_costs
        from realm.economy.markets import tick_order_expiry
        from realm.economy.trade_balance import tick_trade_balance
        from realm.infrastructure.grid_operators import tick_grid_operators
        from realm.infrastructure.grid_utility import tick_grid_utility_connections
        from realm.infrastructure.power_grid import tick_power_grid

        get_oracle(world)
        tick_order_expiry(world)
        tick_grid_operators(world)
        tick_grid_utility_connections(world)
        tick_power_grid(world)
        from realm.infrastructure.utility_billing import tick_monthly_utility_bills

        tick_monthly_utility_bills(world)
        tick_holding_costs(world)
        tick_trade_balance(world)
        tick_research_progress(world)
        tick_era_advancement(world)
        tick_patent_licensing(world)
        tick_research_competition(world)
        for route_data in (world.scenario_state.get("route_daily_volume") or {}).values():
            if isinstance(route_data, dict):
                route_data["units_shipped_today"] = 0
        for entries in (world.scenario_state.get("route_operators") or {}).values():
            if isinstance(entries, list):
                for e in entries:
                    if isinstance(e, dict):
                        e["units_shipped_today"] = 0
    # Phase 8 — Sub-phase 8A: seasonal narration fires on day boundaries.
    # Cheap no-op on every tick except the few days a year that announce
    # spring/summer/autumn/harvest-decline/winter to the world feed.
    tick_seasons(world)
    # Phase 8 — Sub-phase 8B: roll natural disasters (drought, blight, storm,
    # mine collapse, seismic) once per game-day, age + expire active events.
    tick_world_events(world)
    if world.scenario_id == "genesis":
        tick_genesis_feed_tick_scan(world)
        tick_genesis_world_feed(world)
    tick_supply_contract_breaches(world)
    tick_phase2_financial_contracts(world)
    tick_bank_loans(world)
    tick_liens(world)
    tick_home_builders(world)
    tick_assign_homeless_laborers(world)
    if world.scenario_id == "genesis":
        tick_frontier_roads(world)
        tick_laborers(world)
        tick_settler_job_postings(world)
        tick_job_market(world)
        tick_laborer_wages(world)
        tick_laborer_savings(world)
        tick_store_restock(world)
        tick_laborer_spending(world)
        tick_laborer_health(world)
        tick_laborer_births(world)
        tick_laborer_reproduction(world)
        tick_labor_pool_replenishment(world)
        # Phase 7F — inter-island demand: NPCs on food-deficit islands
        # post real B2B grain buy orders against surplus islands. Runs
        # after spending so the day's consumption already drained stores.
        tick_inter_island_buy_orders(world)
    tick_construction_orders(world)
    tick_construction_firms(world)
    tick_business_viability(world)
    tick_nascent_settlements(world)
    record_market_snapshot(world)
    from realm.economy.cpi import tick_cpi

    tick_cpi(world)
    from realm.economy.futures import tick_futures_pipeline

    tick_futures_pipeline(world)
    from realm.economy.fx_market import tick_fx_pipeline

    tick_fx_pipeline(world)
    from realm.economy.currencies import tick_bank_reserves

    tick_bank_reserves(world)
    # Phase 8 — Sub-phase 8D: price panic detection, credit crunch toggle,
    # route blockage lazy-expiry. Reads the snapshot we just recorded.
    tick_market_events(world)
    tick_price_alerts(world)
    if world.scenario_id == "genesis":
        from realm.economy.market_delivery import tick_fob_pickup_hygiene

        tick_fob_pickup_hygiene(world)
        tick_sprint4_feed(world)
        update_margaux_player_profile(world)
        tick_margaux_sprint5_beats(world)

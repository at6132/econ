"""Genesis scenario agents — algorithmic settlers + entrepreneur NPCs.

Phase 7 removes the artificial demand layer entirely:

- Phase 7A: ``pop_hub_*`` parties + the periodic money top-up are gone.
- Phase 7D: the genesis-exchange backstop (``tick_genesis_exchange_quoting``
  and its managed/unmanaged reserves) is *no longer ticked*. The exchange
  keeps its bootstrap inventory but stops auto-listing — it becomes just
  another party. Real demand now comes from ``LaborerNPC`` consumers
  spending wages at entrepreneur-run stores (``tick_laborer_spending``,
  wired in ``tick.advance_tick``).

No Tier-1 timer NPCs: ``advance_tick`` skips ``tick_tier1/tier2`` when
``scenario_id == genesis``.
"""

from __future__ import annotations

from realm.agents.genesis_settlers import tick_settler_business
from realm.agents.settler_identity import tick_settler_world_models
from realm.corporations.acquisitions import tick_acquisition_offers
from realm.corporations.formation import tick_partnership_proposals
from realm.infrastructure.npc_self_roads import tick_npc_self_roads
from realm.intelligence.market_intel import (
    tick_knowledge_decay,
    tick_market_rumors,
    tick_scout_actions,
)
from realm.genesis.exchange_restock import tick_genesis_exchange_restock
from realm.genesis.margaux import tick_genesis_margaux_scripts
from realm.genesis.settler_cycle import tick_genesis_settler_lifecycle
from realm.genesis.broker import tick_survey_broker
from realm.genesis.consolidator import tick_consolidator
from realm.genesis.energy import tick_npc_energy
from realm.contracts.forward import (
    tick_consolidator_forward_proposals,
    tick_settler_forward_proposals,
)
from realm.genesis.shippers import tick_npc_shippers
from realm.population.labor import tick_labor_migration, tick_labor_transport_arrivals
from realm.population.laborers import TICKS_PER_GAME_DAY
from realm.genesis.settler_upgrades import (
    tick_settler_margin_review,
    tick_settler_perishable_sales,
)
from realm.agents.settler_archetypes import tick_researcher_experiments
from realm.contracts.tenders import (
    tick_settler_tender_bidding,
    tick_tender_lifecycle,
)
from realm.deals.bank_loans import tick_loan_repayment
from realm.deals.bilateral_contracts import tick_bilateral_contracts, tick_contract_proposals
from realm.deals.market_tactics import tick_market_cornering, tick_predatory_pricing
from realm.world import World


def tick_genesis_agents(world: World) -> None:
    tick_npc_shippers(world)
    tick_npc_energy(world)
    tick_genesis_exchange_restock(world)
    tick_genesis_settler_lifecycle(world)
    tick_settler_world_models(world)
    tick_partnership_proposals(world)
    tick_acquisition_offers(world)
    tick_knowledge_decay(world)
    tick_scout_actions(world)
    tick_market_rumors(world)
    tick_settler_business(world)
    tick_npc_self_roads(world)
    tick_settler_perishable_sales(world)
    tick_settler_margin_review(world)
    tick_researcher_experiments(world)
    tick_settler_tender_bidding(world)
    tick_tender_lifecycle(world)
    tick_consolidator(world)
    tick_survey_broker(world)
    tick_consolidator_forward_proposals(world)
    tick_settler_forward_proposals(world)
    from realm.genesis.archetypes import tick_archetype_agents

    tick_archetype_agents(world)
    tick_labor_transport_arrivals(world)
    tick_labor_migration(world)
    if world.scenario_id == "genesis":
        now = int(world.tick)
        if now > 0:
            day = TICKS_PER_GAME_DAY
            week = 7 * day
            month = 30 * day
            five_day = 5 * day
            poach = 3 * day
            if now % five_day == 0:
                tick_contract_proposals(world)
            if now % week == 0:
                tick_bilateral_contracts(world)
                tick_market_cornering(world)
                tick_loan_repayment(world)
            if now % month == 0:
                tick_predatory_pricing(world)
            if now % day == 0 or now % poach == 0 or now % week == 0:
                from realm.population.labor_competition import (
                    tick_labor_organizing,
                    tick_labor_poaching,
                    tick_labor_training,
                )

                if now % day == 0:
                    tick_labor_training(world)
                if now % poach == 0:
                    tick_labor_poaching(world)
                if now % week == 0:
                    tick_labor_organizing(world)
                    from realm.geography.land_market import (
                        tick_island_dominance,
                        tick_plot_purchases,
                    )

                    tick_plot_purchases(world)
                    tick_island_dominance(world)
                if now % month == 0:
                    from realm.geography.land_market import tick_plot_abandonment

                    tick_plot_abandonment(world)
    tick_genesis_margaux_scripts(world)

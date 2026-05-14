"""Genesis scenario agents — algorithmic settlers + entrepreneur NPCs.

Phase 7 removes the artificial ``pop_hub_*`` demand layer entirely. There is no
periodic money top-up, no aggregate basket buyer, and no hub-supply contract
proposer. Real demand will be supplied by ``LaborerNPC`` consumers (Phase 7B+)
spending wages at entrepreneur-run stores (Phase 7D); for the duration of 7A
the economy runs without an artificial demand floor.

No Tier-1 timer NPCs: ``advance_tick`` skips ``tick_tier1/tier2`` when
``scenario_id == genesis``.
"""

from __future__ import annotations

from realm.agents_genesis_settlers import tick_settler_business
from realm.genesis_exchange_liquidity import tick_genesis_exchange_quoting
from realm.genesis_margaux_scripts import tick_genesis_margaux_scripts
from realm.genesis_settler_cycle import tick_genesis_settler_lifecycle
from realm.genesis_broker import tick_survey_broker
from realm.genesis_consolidator import tick_consolidator
from realm.genesis_energy import tick_npc_energy
from realm.genesis_forwards import (
    tick_consolidator_forward_proposals,
    tick_settler_forward_proposals,
)
from realm.genesis_shippers import tick_npc_shippers
from realm.labor import tick_labor_migration, tick_labor_transport_arrivals
from realm.settler_upgrades import tick_settler_margin_review
from realm.tenders import (
    tick_settler_tender_bidding,
    tick_tender_lifecycle,
)
from realm.world import World


def tick_genesis_agents(world: World) -> None:
    tick_genesis_exchange_quoting(world)
    tick_npc_shippers(world)
    tick_npc_energy(world)
    tick_genesis_settler_lifecycle(world)
    tick_settler_business(world)
    tick_settler_margin_review(world)
    tick_settler_tender_bidding(world)
    tick_tender_lifecycle(world)
    tick_consolidator(world)
    tick_survey_broker(world)
    tick_consolidator_forward_proposals(world)
    tick_settler_forward_proposals(world)
    from realm.genesis_archetypes import tick_archetype_agents

    tick_archetype_agents(world)
    tick_labor_transport_arrivals(world)
    tick_labor_migration(world)
    tick_genesis_exchange_quoting(world)
    tick_genesis_margaux_scripts(world)

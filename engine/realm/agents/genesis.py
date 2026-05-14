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
from realm.genesis.settler_upgrades import tick_settler_margin_review
from realm.contracts.tenders import (
    tick_settler_tender_bidding,
    tick_tender_lifecycle,
)
from realm.world import World


def tick_genesis_agents(world: World) -> None:
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
    from realm.genesis.archetypes import tick_archetype_agents

    tick_archetype_agents(world)
    tick_labor_transport_arrivals(world)
    tick_labor_migration(world)
    tick_genesis_margaux_scripts(world)

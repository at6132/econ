"""Genesis scenario agents — aggregate population demand + algorithmic settlers.

No Tier-1 timer NPCs; ``advance_tick`` skips ``tick_tier1/tier2`` when ``scenario_id == genesis``.
"""

from __future__ import annotations

from realm.agents_genesis_settlers import tick_settler_business
from realm.genesis_contracts import tick_genesis_pop_hub_contracts
from realm.genesis_digest import tick_genesis_world_feed
from realm.genesis_exchange_liquidity import tick_genesis_exchange_quoting
from realm.genesis_margaux_scripts import tick_genesis_margaux_scripts
from realm.ids import MaterialId, PartyId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.markets import market_buy
from realm.world import World

POP_HUBS: tuple[PartyId, ...] = (PartyId("pop_hub_e"), PartyId("pop_hub_w"))

# Re-seed hub wallets when they run low (money creation channel — visible, from system reserve).
_GENESIS_HUB_LOW_CASH_CENTS = 1_500_000  # $15,000
_GENESIS_HUB_TOPUP_CENTS = 20_000_000  # $200,000 per top-up


def _genesis_pop_hub_topup(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    reserve = system_reserve_account()
    for hub in POP_HUBS:
        if hub not in world.parties:
            continue
        acct = party_cash_account(hub)
        if world.ledger.balance(acct) >= _GENESIS_HUB_LOW_CASH_CENTS:
            continue
        tr = world.ledger.transfer(
            debit=reserve,
            credit=acct,
            amount_cents=_GENESIS_HUB_TOPUP_CENTS,
        )
        if isinstance(tr, MoneyErr):
            break


def tick_population_demands(world: World) -> None:
    """
    Population hubs are **takers**: every tick they ``market_buy`` staples at the best ask.

    ``market_buy`` only logs ``market_buy`` events when fills occur — with an empty book it
    returns ``ok: false`` silently; ``tick_genesis_exchange_quoting`` runs first to keep asks up.
    """
    if world.scenario_id != "genesis":
        return
    for hub in POP_HUBS:
        if hub not in world.parties:
            continue
        market_buy(world, hub, MaterialId("coal"), 28)
        market_buy(world, hub, MaterialId("grain"), 24)
        market_buy(world, hub, MaterialId("electricity"), 28)
        market_buy(world, hub, MaterialId("timber"), 18)


def tick_genesis_agents(world: World) -> None:
    tick_genesis_exchange_quoting(world)
    _genesis_pop_hub_topup(world)
    tick_population_demands(world)
    tick_settler_business(world)
    tick_genesis_margaux_scripts(world)
    tick_genesis_pop_hub_contracts(world)
    tick_genesis_world_feed(world)

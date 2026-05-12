"""Genesis scenario agents — aggregate population demand + algorithmic settlers.

No Tier-1 timer NPCs; ``advance_tick`` skips ``tick_tier1/tier2`` when ``scenario_id == genesis``.
"""

from __future__ import annotations

from realm.agents_genesis_settlers import tick_settler_business
from realm.genesis_contracts import tick_genesis_pop_hub_contracts
from realm.genesis_digest import tick_genesis_world_feed
from realm.genesis_margaux_opener import tick_genesis_margaux_script_opener
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
    Population hubs lift resting asks (aggressive ``market_buy``) — demand floor tracks supply price.
    No resting bid churn: volume clears against ``genesis_exchange`` and player/settler asks.
    """
    if world.scenario_id != "genesis":
        return
    tg = world.tick
    hub_e, hub_w = POP_HUBS
    if hub_e in world.parties:
        if tg % 3 == 0:
            market_buy(world, hub_e, MaterialId("electricity"), 22)
        if tg % 4 == 1:
            market_buy(world, hub_e, MaterialId("coal"), 18)
        if tg % 5 == 2:
            market_buy(world, hub_e, MaterialId("grain"), 16)
        if tg % 7 == 3:
            market_buy(world, hub_e, MaterialId("timber"), 12)
    if hub_w in world.parties:
        if tg % 3 == 2:
            market_buy(world, hub_w, MaterialId("electricity"), 18)
        if tg % 4 == 0:
            market_buy(world, hub_w, MaterialId("coal"), 14)
        if tg % 5 == 1:
            market_buy(world, hub_w, MaterialId("grain"), 18)
        if tg % 7 == 5:
            market_buy(world, hub_w, MaterialId("timber"), 10)


def tick_genesis_agents(world: World) -> None:
    _genesis_pop_hub_topup(world)
    tick_population_demands(world)
    tick_settler_business(world)
    tick_genesis_margaux_script_opener(world)
    tick_genesis_pop_hub_contracts(world)
    tick_genesis_world_feed(world)

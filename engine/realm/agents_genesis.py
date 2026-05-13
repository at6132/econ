"""Genesis scenario agents — aggregate population demand + algorithmic settlers.

No Tier-1 timer NPCs; ``advance_tick`` skips ``tick_tier1/tier2`` when ``scenario_id == genesis``.
"""

from __future__ import annotations

from realm.agents_genesis_settlers import tick_settler_business
from realm.genesis_contracts import tick_genesis_pop_hub_contracts
from realm.genesis_exchange_liquidity import tick_genesis_exchange_quoting
from realm.genesis_margaux_scripts import tick_genesis_margaux_scripts
from realm.genesis_pricing import hub_max_bid_cents
from realm.genesis_settler_cycle import tick_genesis_settler_lifecycle
from realm.genesis_shippers import tick_npc_shippers
from realm.settler_upgrades import tick_settler_margin_review
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
    Population hubs are **takers**: each tick they ``market_buy`` a basket of staples and
    mid-chain goods so producer asks clear (``market_buy`` walks price levels and skips
    counterparty rep gates that block the cheapest clip).

    In ``tick_genesis_agents`` this runs **after** settler business so listings and output sells
    posted this tick are visible before the hub sweep (price-time priority still requires a sorted
    book; see ``market_buy``).

    ``tick_genesis_exchange_quoting`` runs before settlers (inputs) and again after hub demand so
    the book stays liquid and ends each tick with visible exchange clips for the next tick.
    """
    if world.scenario_id != "genesis":
        return
    basket: tuple[tuple[MaterialId, int], ...] = (
        (MaterialId("coal"), 40),
        (MaterialId("grain"), 36),
        (MaterialId("electricity"), 40),
        (MaterialId("timber"), 28),
        (MaterialId("lumber"), 22),
        (MaterialId("brick"), 16),
        (MaterialId("rope"), 18),
        (MaterialId("flour"), 14),
        (MaterialId("iron_ingot"), 8),
        (MaterialId("copper_ingot"), 8),
        (MaterialId("bread"), 12),
        (MaterialId("charcoal"), 14),
    )
    for hub in POP_HUBS:
        if hub not in world.parties:
            continue
        for mid, clip in basket:
            market_buy(
                world,
                hub,
                mid,
                clip,
                max_price_per_unit_cents=hub_max_bid_cents(mid),
            )


def tick_genesis_agents(world: World) -> None:
    _genesis_pop_hub_topup(world)
    tick_genesis_exchange_quoting(world)
    tick_npc_shippers(world)
    tick_genesis_settler_lifecycle(world)
    tick_settler_business(world)
    tick_settler_margin_review(world)
    tick_population_demands(world)
    tick_genesis_exchange_quoting(world)
    tick_genesis_margaux_scripts(world)
    tick_genesis_pop_hub_contracts(world)

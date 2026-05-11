"""Genesis scenario agents — aggregate population demand + algorithmic settlers.

No Tier-1 timer NPCs; ``advance_tick`` skips ``tick_tier1/tier2`` when ``scenario_id == genesis``.
"""

from __future__ import annotations

from realm.actions import SURVEY_COST_CENTS, claim_plot, survey_plot
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account
from realm.markets import market_buy, place_sell_order
from realm.world import World

POP_HUBS: tuple[PartyId, ...] = (PartyId("pop_hub_e"), PartyId("pop_hub_w"))


def _plots_manhattan_order(world: World) -> list[PlotId]:
    if not world.plots:
        return []
    xs = [p.x for p in world.plots.values()]
    ys = [p.y for p in world.plots.values()]
    cx = (min(xs) + max(xs)) // 2
    cy = (min(ys) + max(ys)) // 2
    ordered = sorted(
        world.plots.values(),
        key=lambda p: (abs(p.x - cx) + abs(p.y - cy), p.x, p.y),
    )
    return [p.plot_id for p in ordered]


def _first_owned_plot(world: World, party: PartyId) -> PlotId | None:
    for pid, pl in world.plots.items():
        if pl.owner == party:
            return pid
    return None


def tick_population_demands(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    if world.tick % 6 != 0:
        return
    hub_e, hub_w = POP_HUBS
    if hub_e in world.parties:
        market_buy(world, hub_e, MaterialId("grain"), 2)
    if hub_w in world.parties:
        market_buy(world, hub_w, MaterialId("grain"), 1)
    if world.tick % 12 == 0 and hub_e in world.parties:
        market_buy(world, hub_e, MaterialId("electricity"), 2)
    if world.tick % 14 == 0 and hub_w in world.parties:
        market_buy(world, hub_w, MaterialId("coal"), 1)


def tick_settler_agents(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    scan = _plots_manhattan_order(world)
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    for party in settlers:
        owned = _first_owned_plot(world, party)
        if owned is None:
            for pid in scan:
                plot = world.plots[pid]
                if plot.owner is None:
                    claim_plot(world, party, pid)
                    break
            continue
        suf = str(party).removeprefix("settler_")
        try:
            idx = int(suf)
        except ValueError:
            idx = 0
        # Stagger survey / market / listings so not all 50 fire the same tick (claims stay greedy).
        if (world.tick + idx) % 3 != 0:
            continue
        plot = world.plots[owned]
        if not plot.surveyed:
            cash = world.ledger.balance(party_cash_account(party))
            if cash >= SURVEY_COST_CENTS:
                survey_plot(world, party, owned)
            continue
        if world.inventory.qty(party, MaterialId("grain")) == 0:
            market_buy(world, party, MaterialId("grain"), 1)
        if world.tick % 13 == idx % 13:
            if world.inventory.qty(party, MaterialId("timber")) >= 2:
                place_sell_order(world, party, MaterialId("timber"), 2, 82)


def tick_genesis_agents(world: World) -> None:
    tick_population_demands(world)
    tick_settler_agents(world)

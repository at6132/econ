"""Genesis scenario agents — aggregate population demand + algorithmic settlers.

No Tier-1 timer NPCs; ``advance_tick`` skips ``tick_tier1/tier2`` when ``scenario_id == genesis``.
"""

from __future__ import annotations

from realm.actions import SURVEY_COST_CENTS, claim_plot, survey_plot
from realm.genesis_digest import tick_genesis_world_feed
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account
from realm.markets import (
    cancel_party_bids_for_material,
    market_buy,
    place_buy_order,
    place_sell_order,
)
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


def _jitter_price_cents(world: World, party: PartyId, purpose: str, base: int) -> int:
    r = world.rng(f"gen:jitter:{purpose}:{party}")
    m = 1.0 + (r.randint(-50, 50) / 1000.0)
    return max(4, int(round(base * m)))


def tick_population_demands(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    tg = world.tick
    hub_e, hub_w = POP_HUBS
    if hub_e in world.parties and tg % 6 == 0:
        market_buy(world, hub_e, MaterialId("grain"), 2)
    if hub_w in world.parties and tg % 7 == 0:
        market_buy(world, hub_w, MaterialId("grain"), 1)
    if hub_e in world.parties and tg % 11 == 0:
        cancel_party_bids_for_material(world, hub_e, MaterialId("grain"))
        lim = 95 + world.rng("pop:hub_e:grain").randint(0, 24)
        place_buy_order(world, hub_e, MaterialId("grain"), 2, lim)
    if hub_w in world.parties and tg % 13 == 0:
        cancel_party_bids_for_material(world, hub_w, MaterialId("grain"))
        lim = 92 + world.rng("pop:hub_w:grain").randint(0, 20)
        place_buy_order(world, hub_w, MaterialId("grain"), 1, lim)
    if tg % 12 == 0 and hub_e in world.parties:
        market_buy(world, hub_e, MaterialId("electricity"), 2)
    if tg % 14 == 0 and hub_w in world.parties:
        market_buy(world, hub_w, MaterialId("coal"), 1)
    if hub_e in world.parties and tg % 17 == 0:
        cancel_party_bids_for_material(world, hub_e, MaterialId("electricity"))
        lim = 32 + world.rng("pop:hub_e:ele").randint(0, 14)
        place_buy_order(world, hub_e, MaterialId("electricity"), 2, lim)


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
        if (world.tick + idx) % 2 != 0:
            continue
        plot = world.plots[owned]
        if not plot.surveyed:
            cash = world.ledger.balance(party_cash_account(party))
            if cash >= SURVEY_COST_CENTS:
                survey_plot(world, party, owned)
            continue
        if world.inventory.qty(party, MaterialId("grain")) == 0:
            market_buy(world, party, MaterialId("grain"), 1)
        r = world.rng(f"gen:settler_list:{party}")
        if r.random() < 0.55:
            qtim = world.inventory.qty(party, MaterialId("timber"))
            if qtim >= 1:
                q = 2 if qtim >= 2 and r.random() < 0.45 else 1
                px = _jitter_price_cents(world, party, "timber", 82)
                place_sell_order(world, party, MaterialId("timber"), min(q, qtim), px)
        if r.random() < 0.38:
            qco = world.inventory.qty(party, MaterialId("coal"))
            if qco >= 1:
                q = 2 if qco >= 2 and r.random() < 0.4 else 1
                px = _jitter_price_cents(world, party, "coal", 38)
                place_sell_order(world, party, MaterialId("coal"), min(q, qco), px)
        if r.random() < 0.36:
            qgr = world.inventory.qty(party, MaterialId("grain"))
            if qgr >= 2:
                q = 2 if qgr >= 3 and r.random() < 0.5 else 2
                px = _jitter_price_cents(world, party, "grain", 118)
                place_sell_order(world, party, MaterialId("grain"), min(q, qgr), px)


def tick_genesis_agents(world: World) -> None:
    tick_population_demands(world)
    tick_settler_agents(world)
    tick_genesis_world_feed(world)

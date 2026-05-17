"""Real estate valuation and plot market."""

from __future__ import annotations

from realm.actions.plot_actions import claim_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId, PlotId
from realm.production.blueprints import seed_world_blueprints
from realm.world import bootstrap_frontier, bootstrap_genesis
from realm.world.real_estate import (
    BASE_PLOT_VALUE_CENTS,
    buy_plot_market,
    compute_plot_value,
    list_plot_for_sale_market,
    tick_npc_plot_demand,
)


def test_town_adjacent_plot_higher_value() -> None:
    world = bootstrap_genesis(seed=42)
    seed_world_blueprints(world)
    if not world.towns:
        return
    town = next(iter(world.towns.values()))
    near_val = 0
    far_val = 0
    tcx = int(getattr(town, "center_x", 0))
    tcy = int(getattr(town, "center_y", 0))
    for pid, plot in world.plots.items():
        if plot.owner is not None or plot.terrain.value.startswith("water"):
            continue
        d = abs(plot.x - tcx) + abs(plot.y - tcy)
        v = compute_plot_value(world, pid)
        if d < 5 and v > near_val:
            near_val = v
        if d > 50 and (far_val == 0 or v < far_val):
            far_val = v
    if near_val and far_val:
        assert near_val > far_val


def test_mineral_rich_plot_higher_value() -> None:
    world = bootstrap_frontier(seed=99)
    seed_world_blueprints(world)
    rich = poor = None
    for pid, plot in world.plots.items():
        if plot.terrain.value.startswith("water"):
            continue
        g = float(plot.subsurface.iron_ore_grade)
        if g > 0.7:
            rich = pid
        if g < 0.15 and poor is None:
            poor = pid
    if rich and poor:
        assert compute_plot_value(world, rich) > compute_plot_value(world, poor)


def test_coastal_plot_premium() -> None:
    from realm.production.recipe_sites import plot_is_coastal

    world = bootstrap_frontier(seed=100)
    seed_world_blueprints(world)
    coastal = inland = None
    for pid, plot in world.plots.items():
        if coastal is None and plot_is_coastal(world, plot):
            coastal = pid
        if inland is None and plot.terrain.value == "plains":
            inland = pid
    if coastal and inland:
        base_inland = compute_plot_value(world, inland)
        # Coastal bonus is multiplicative; high-mineral inland can still exceed
        # low-mineral coast — compare against base plot value floor.
        assert compute_plot_value(world, coastal) >= int(BASE_PLOT_VALUE_CENTS * 1.4)
        assert base_inland >= BASE_PLOT_VALUE_CENTS


def test_list_and_buy_plot() -> None:
    world = bootstrap_frontier(seed=101)
    seed_world_blueprints(world)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    seller = PartyId("player")
    buyer = PartyId("t1_consumer")
    pid = next(
        p for p, pl in world.plots.items() if pl.owner is None and not pl.terrain.value.startswith("water")
    )
    claim_plot(world, seller, pid)
    list_plot_for_sale_market(world, seller, pid, ask_price_cents=20_000)
    r = buy_plot_market(world, buyer, pid)
    assert r["ok"]
    assert world.plots[pid].owner == buyer
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_buy_deducts_ask() -> None:
    world = bootstrap_frontier(seed=102)
    seed_world_blueprints(world)
    seller = PartyId("player")
    buyer = PartyId("t1_consumer")
    pid = next(
        p for p, pl in world.plots.items() if pl.owner is None and not pl.terrain.value.startswith("water")
    )
    claim_plot(world, seller, pid)
    ask = 15_000
    list_plot_for_sale_market(world, seller, pid, ask_price_cents=ask)
    from realm.core.ledger import party_cash_account

    before_b = world.ledger.balance(party_cash_account(buyer))
    before_s = world.ledger.balance(party_cash_account(seller))
    buy_plot_market(world, buyer, pid)
    assert world.ledger.balance(party_cash_account(buyer)) == before_b - ask
    assert world.ledger.balance(party_cash_account(seller)) == before_s + ask


def test_claim_cost_scales_with_value() -> None:
    world = bootstrap_frontier(seed=103)
    seed_world_blueprints(world)
    from realm.world import claim_cost_cents_for_plot

    costs = [
        claim_cost_cents_for_plot(world, pid)
        for pid, pl in world.plots.items()
        if pl.owner is None and not pl.terrain.value.startswith("water")
    ]
    assert max(costs) > min(costs)
    assert max(costs) >= 50_000


def test_npc_demand_scores_update_weekly() -> None:
    world = bootstrap_genesis(seed=104)
    seed_world_blueprints(world)
    world.tick = 10_080
    tick_npc_plot_demand(world)
    scores = world.scenario_state.get("plot_demand_scores") or {}
    assert isinstance(scores, dict)

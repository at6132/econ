"""Tests for geography land market — listings, premiums, dominance."""

from __future__ import annotations

from realm.agents.settler_identity import assign_settler_personality
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.geography.land_market import (
    HIGH_SOCIAL_RADIUS,
    apply_island_dominance_toll,
    list_plot_for_sale,
    listing_valuation_cents,
    tick_island_dominance,
    tick_location_premium,
    tick_plot_purchases,
)
from realm.production.blueprints import seed_world_blueprints
from realm.world import bootstrap_genesis
from realm.world.world import claim_cost_cents_for_plot


def _first_unowned_plot(world) -> PlotId:
    for pid, plot in world.plots.items():
        if plot.owner is None and not plot.terrain.value.startswith("water"):
            return pid
    raise AssertionError("no unowned plot")


def test_tick_location_premium_stores_scores() -> None:
    world = bootstrap_genesis(seed=7, grid_width=48, grid_height=36, settler_count=4)
    scores = world.scenario_state.get("plot_location_scores") or {}
    assert scores
    assert all(0.0 <= float(v) <= 1.0 for v in scores.values())


def test_claim_cost_scales_with_location_score() -> None:
    world = bootstrap_genesis(seed=11, grid_width=48, grid_height=36, settler_count=4)
    pid = _first_unowned_plot(world)
    scores = world.scenario_state.setdefault("plot_location_scores", {})
    scores[str(pid)] = 0.0
    base = claim_cost_cents_for_plot(world, pid)
    scores[str(pid)] = 1.0
    boosted = claim_cost_cents_for_plot(world, pid)
    assert boosted > base
    assert boosted == int(base * 1.5)


def test_list_plot_for_sale_rejects_active_production() -> None:
    world = bootstrap_genesis(seed=13, grid_width=48, grid_height=36, settler_count=4)
    seed_world_blueprints(world)
    seller = PartyId("settler_001")
    plot = next(
        (p for p in world.plots.values() if p.owner == seller),
        None,
    )
    if plot is None:
        plot = next(
            p
            for p in world.plots.values()
            if p.owner is None and not p.terrain.value.startswith("water")
        )
        plot.owner = seller
    from realm.world import ActiveProduction

    world.active_production.append(
        ActiveProduction(
            run_id="test-run",
            party=seller,
            plot_id=plot.plot_id,
            recipe_id="grow_grain",
            ticks_remaining=100,
        )
    )
    res = list_plot_for_sale(world, seller, plot.plot_id, 100_000)
    assert not res["ok"]


def test_tick_plot_purchases_conserves_money() -> None:
    world = bootstrap_genesis(seed=17, grid_width=48, grid_height=36, settler_count=4)
    seed_world_blueprints(world)
    buyer = PartyId("settler_002")
    seller = PartyId("settler_003")
    assign_settler_personality(world, buyer)
    assign_settler_personality(world, seller)
    store = world.scenario_state.setdefault("settler_identities", {})
    store[str(buyer)]["personality"]["social_radius"] = HIGH_SOCIAL_RADIUS
    unowned = [
        p
        for p in world.plots.values()
        if p.owner is None and not p.terrain.value.startswith("water")
    ]
    buyer_plot = unowned[0]
    buyer_plot.owner = buyer
    seller_plot = next(
        p
        for p in unowned[1:]
        if abs(p.x - buyer_plot.x) + abs(p.y - buyer_plot.y) <= 5
    )
    seller_plot.owner = seller
    ask = 1_000
    list_plot_for_sale(world, seller, seller_plot.plot_id, ask)
    buyer_acct = party_cash_account(buyer)
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=buyer_acct,
        amount_cents=500_000,
    )
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    world.tick = 7 * TICKS_PER_GAME_DAY
    tick_plot_purchases(world)
    assert world.plots[seller_plot.plot_id].owner == buyer
    assert_money_conserved(world.ledger, snap.ledger_total_cents)
    assert listing_valuation_cents(world, seller_plot.plot_id) > int(ask * 1.1)


def test_island_dominance_toll_conserves_money() -> None:
    world = bootstrap_genesis(seed=19, grid_width=48, grid_height=36, settler_count=4)
    shipper = PartyId("settler_004")
    world.scenario_state["island_dominance"] = {
        "0": {
            "entity_key": f"party:{shipper}",
            "share": 0.75,
            "productive_plots": 3,
            "total_productive": 4,
            "declared_tick": 0,
        }
    }
    origin = next(
        p.plot_id
        for p in world.plots.values()
        if world.scenario_state.get("plot_islands", {}).get(str(p.plot_id)) == 0
    )
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    paid, _ = apply_island_dominance_toll(world, shipper, origin, 100_000)
    assert paid == 5_000
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_tick_island_dominance_flags_majority_holder() -> None:
    world = bootstrap_genesis(seed=23, grid_width=48, grid_height=36, settler_count=4)
    seed_world_blueprints(world)
    holder = PartyId("settler_005")
    islands_map = world.scenario_state.get("plot_islands") or {}
    island_plots = [
        PlotId(pid_s)
        for pid_s, isl in islands_map.items()
        if int(isl) == 0
    ]
    world.plot_buildings = [
        b
        for b in world.plot_buildings
        if not (
            int(islands_map.get(str(b.get("plot_id")), -1)) == 0
            and str(b.get("building_id")) != "residence"
        )
    ]
    for pid_s in list(world.plot_placed_buildings):
        if int(islands_map.get(pid_s, -1)) != 0:
            continue
        kept_iids: list[str] = []
        for iid in world.plot_placed_buildings.get(pid_s, []):
            pb = world.placed_buildings.get(iid)
            if pb is not None and str(getattr(pb, "blueprint_id", "")) == "residence":
                kept_iids.append(iid)
            else:
                world.placed_buildings.pop(iid, None)
        if kept_iids:
            world.plot_placed_buildings[pid_s] = kept_iids
        else:
            world.plot_placed_buildings.pop(pid_s, None)
    for pid in island_plots[:8]:
        plot = world.plots[pid]
        plot.owner = holder
        world.plot_buildings.append(
            {
                "party": str(holder),
                "plot_id": str(pid),
                "building_id": "workshop",
                "completes_at_tick": 0,
            }
        )
    world.tick = 7 * TICKS_PER_GAME_DAY
    tick_island_dominance(world)
    dom = world.scenario_state.get("island_dominance") or {}
    assert "0" in dom
    assert dom["0"]["entity_key"] == f"party:{holder}"

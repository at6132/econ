"""Plot subdivision into sub-plots."""

from __future__ import annotations

from realm.actions.blueprint_actions import place_blueprint
from realm.actions.plot_actions import (
    buy_sub_plot,
    claim_plot,
    list_sub_plot_for_sale,
    subdivide_plot,
)
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId
from realm.production.blueprints import seed_world_blueprints
from realm.world import bootstrap_frontier


def _claim_land(world, party: PartyId = PartyId("player")):
    pid = next(
        p
        for p, pl in world.plots.items()
        if pl.owner is None and not pl.terrain.value.startswith("water")
    )
    claim_plot(world, party, pid)
    return pid


def test_subdivide_into_2() -> None:
    world = bootstrap_frontier(seed=200)
    seed_world_blueprints(world)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    party = PartyId("player")
    pid = _claim_land(world, party)
    r = subdivide_plot(
        world,
        party,
        pid,
        [
            {"grid_x": 0, "grid_y": 0, "grid_w": 5, "grid_h": 10},
            {"grid_x": 5, "grid_y": 0, "grid_w": 5, "grid_h": 10},
        ],
    )
    assert r["ok"], r
    assert len(r["sub_plot_ids"]) == 2
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_subdivide_rejects_gap() -> None:
    world = bootstrap_frontier(seed=201)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _claim_land(world, party)
    r = subdivide_plot(
        world,
        party,
        pid,
        [
            {"grid_x": 0, "grid_y": 0, "grid_w": 5, "grid_h": 10},
            {"grid_x": 6, "grid_y": 0, "grid_w": 4, "grid_h": 10},
        ],
    )
    assert not r["ok"]


def test_subdivide_rejects_overlap() -> None:
    world = bootstrap_frontier(seed=202)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _claim_land(world, party)
    r = subdivide_plot(
        world,
        party,
        pid,
        [
            {"grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 10},
            {"grid_x": 4, "grid_y": 0, "grid_w": 6, "grid_h": 10},
        ],
    )
    assert not r["ok"]


def test_subdivide_minimum_size() -> None:
    world = bootstrap_frontier(seed=203)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _claim_land(world, party)
    r = subdivide_plot(
        world,
        party,
        pid,
        [
            {"grid_x": 0, "grid_y": 0, "grid_w": 1, "grid_h": 10},
            {"grid_x": 1, "grid_y": 0, "grid_w": 9, "grid_h": 10},
        ],
    )
    assert not r["ok"]


def test_subdivide_max_9() -> None:
    world = bootstrap_frontier(seed=204)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _claim_land(world, party)
    parts = [{"grid_x": i % 10, "grid_y": 0, "grid_w": 1, "grid_h": 2} for i in range(10)]
    r = subdivide_plot(world, party, pid, parts)
    assert not r["ok"]


def test_build_on_sub_plot() -> None:
    world = bootstrap_frontier(seed=205)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _claim_land(world, party)
    r = subdivide_plot(
        world,
        party,
        pid,
        [
            {"grid_x": 0, "grid_y": 0, "grid_w": 5, "grid_h": 10},
            {"grid_x": 5, "grid_y": 0, "grid_w": 5, "grid_h": 10},
        ],
    )
    sp_id = r["sub_plot_ids"][0]
    pr = place_blueprint(
        world,
        party,
        pid,
        "watch_hut",
        0,
        0,
        build_mode="turnkey",
        sub_plot_id=sp_id,
    )
    assert pr["ok"], pr


def test_sub_plot_sale() -> None:
    world = bootstrap_frontier(seed=206)
    seed_world_blueprints(world)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    seller = PartyId("player")
    buyer = PartyId("t1_consumer")
    pid = _claim_land(world, seller)
    r = subdivide_plot(
        world,
        seller,
        pid,
        [
            {"grid_x": 0, "grid_y": 0, "grid_w": 5, "grid_h": 10},
            {"grid_x": 5, "grid_y": 0, "grid_w": 5, "grid_h": 10},
        ],
    )
    sp_id = r["sub_plot_ids"][0]
    list_sub_plot_for_sale(world, seller, sp_id, 10_000)
    br = buy_sub_plot(world, buyer, sp_id)
    assert br["ok"]
    assert world.sub_plots[sp_id].owner == str(buyer)
    assert_money_conserved(world.ledger, snap.ledger_total_cents)

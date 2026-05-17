"""Blueprint system — seeded catalog, placement, licensing."""

from __future__ import annotations

from realm.actions.blueprint_actions import create_blueprint, place_blueprint
from realm.actions.plot_actions import claim_plot
from realm.core.conservation import (
    ConservationSnapshot,
    assert_money_conserved,
)
from realm.core.ids import PartyId, PlotId
from realm.production.blueprints import SEEDED_BLUEPRINTS, seed_world_blueprints
from realm.production.buildings import build_on_plot
from realm.world import bootstrap_frontier

_SEEDED_WORKSHOPS = (
    "strip_mine",
    "foundry",
    "timber_yard",
    "grain_row",
    "gristmill",
    "power_shed",
    "wood_shop",
    "stone_works",
    "kiln_shed",
    "residence",
    "store",
    "dock",
    "waystation",
    "tidal_mill",
    "apothecary",
    "laboratory",
    "blast_furnace",
    "forge_press",
    "tool_workshop",
    "assay_lab",
    "bank_building",
)


def _unclaimed_land(world, *, coastal: bool = False) -> PlotId:
    for pid, plot in world.plots.items():
        if plot.owner is not None:
            continue
        if str(plot.terrain.value).startswith("water"):
            continue
        from realm.production.recipe_sites import plot_is_coastal

        is_coast = plot_is_coastal(world, plot)
        if coastal and not is_coast:
            continue
        if not coastal and is_coast:
            continue
        return pid
    raise AssertionError("no suitable plot")


def test_seeded_blueprints_all_present() -> None:
    assert len(_SEEDED_WORKSHOPS) >= 20
    for bid in _SEEDED_WORKSHOPS:
        assert bid in SEEDED_BLUEPRINTS


def test_create_custom_blueprint() -> None:
    world = bootstrap_frontier(seed=7)
    seed_world_blueprints(world)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    party = PartyId("player")
    r = create_blueprint(
        world,
        party,
        name="Custom Shed",
        description="test",
        footprint_w=2,
        footprint_h=2,
        construction_materials={"timber": 2},
        construction_labor_cents=10_000,
        construction_ticks=60,
        enabled_recipe_ids=[],
        maintenance_interval_ticks=0,
        maintenance_materials={},
        maintenance_grace_ticks=0,
        is_public=True,
        license_fee_cents=0,
        category="custom",
        terrain_requirements=[],
        requires_coastal=False,
        requires_power=False,
    )
    assert r["ok"]
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_place_seeded_blueprint() -> None:
    world = bootstrap_frontier(seed=8)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _unclaimed_land(world)
    claim_plot(world, party, pid)
    r = place_blueprint(world, party, pid, "field_stockade", 0, 0, build_mode="turnkey")
    assert r["ok"], r
    iid = str(r["instance_id"])
    assert iid in world.placed_buildings


def test_place_rejects_overlap() -> None:
    world = bootstrap_frontier(seed=9)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _unclaimed_land(world)
    claim_plot(world, party, pid)
    assert place_blueprint(world, party, pid, "field_stockade", 0, 0, build_mode="turnkey")["ok"]
    r2 = place_blueprint(world, party, pid, "watch_hut", 1, 0, build_mode="turnkey")
    assert not r2["ok"]


def test_place_rejects_out_of_bounds() -> None:
    world = bootstrap_frontier(seed=10)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _unclaimed_land(world)
    claim_plot(world, party, pid)
    r = place_blueprint(world, party, pid, "strip_mine", 9, 0, build_mode="self")
    assert not r["ok"]


def test_place_terrain_gate() -> None:
    world = bootstrap_frontier(seed=11)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _unclaimed_land(world, coastal=False)
    claim_plot(world, party, pid)
    r = place_blueprint(world, party, pid, "dock", 0, 0, build_mode="self")
    assert not r["ok"]


def test_license_fee_paid_on_place() -> None:
    world = bootstrap_frontier(seed=12)
    seed_world_blueprints(world)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    creator = PartyId("t1_consumer")
    buyer = PartyId("player")
    r = create_blueprint(
        world,
        creator,
        name="Licensed Hut",
        description="fee test",
        footprint_w=1,
        footprint_h=1,
        construction_materials={},
        construction_labor_cents=0,
        construction_ticks=0,
        enabled_recipe_ids=[],
        maintenance_interval_ticks=0,
        maintenance_materials={},
        maintenance_grace_ticks=0,
        is_public=True,
        license_fee_cents=5_000,
        category="custom",
        terrain_requirements=[],
        requires_coastal=False,
        requires_power=False,
    )
    bid = str(r["blueprint_id"])
    pid = _unclaimed_land(world)
    claim_plot(world, buyer, pid)
    pr = place_blueprint(world, buyer, pid, bid, 0, 0, build_mode="self")
    assert pr["ok"]
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_backward_compat_build_on_plot() -> None:
    world = bootstrap_frontier(seed=13)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _unclaimed_land(world)
    claim_plot(world, party, pid)
    r = build_on_plot(world, party, pid, "field_stockade", build_mode="turnkey")
    assert r["ok"], r
    assert world.plot_buildings

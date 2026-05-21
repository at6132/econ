"""Blueprint system — seeded catalog, placement, licensing."""

from __future__ import annotations

from realm.actions.blueprint_actions import (
    blueprints_visible_to,
    compute_turnkey_cost_cents,
    create_blueprint,
    place_blueprint,
)
from realm.actions.plot_actions import claim_plot
from realm.core.conservation import (
    ConservationSnapshot,
    assert_money_conserved,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
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


def test_dock_rejects_inland_placement_on_coastal_parcel() -> None:
    """Coastal deed with room inland: dock must overlap waterfront cells."""
    from realm.core.ids import PlotId
    from realm.production.recipe_sites import footprint_borders_water, waterfront_build_cells
    from realm.world.plot_parcels import refresh_world_cell_index
    from realm.world.terrain import Terrain
    from realm.world.plot_scale import cells_free

    world = bootstrap_frontier(seed=21, grid_width=8, grid_height=8, uniform_plots=True)
    seed_world_blueprints(world)
    plot = world.plots[PlotId("p-2-2")]
    plot.terrain = Terrain.PLAINS
    plot.world_cells = ((2, 2), (3, 2), (2, 3), (3, 3))
    world.plots[PlotId("p-1-2")].terrain = Terrain.WATER_SHALLOW
    world.plots[PlotId("p-1-3")].terrain = Terrain.WATER_SHALLOW
    refresh_world_cell_index(world)
    front = waterfront_build_cells(world, plot)
    assert front
    party = PartyId("player")
    claim_plot(world, party, PlotId("p-2-2"))
    inland: tuple[int, int] | None = None
    for gy in range(20):
        for gx in range(20):
            if not cells_free(str(plot.plot_id), world, gx, gy, 4, 2):
                continue
            if not footprint_borders_water(world, plot, gx, gy, 4, 2):
                inland = (gx, gy)
                break
        if inland is not None:
            break
    assert inland is not None
    r = place_blueprint(
        world, party, plot.plot_id, "dock", inland[0], inland[1], build_mode="self"
    )
    assert not r["ok"]
    assert "waterfront" in str(r.get("reason", ""))


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


def test_turnkey_cost_uses_fair_value_when_book_empty() -> None:
    world = bootstrap_frontier(seed=14)
    seed_world_blueprints(world)
    world.market_asks_by_material.clear()
    bp = world.blueprints["blast_furnace"]
    cost = compute_turnkey_cost_cents(world, bp)
    assert cost < 2_000_000
    assert cost > bp.construction_labor_cents
    rows = blueprints_visible_to(world, PartyId("player"))
    row = next(r for r in rows if r["blueprint_id"] == "blast_furnace")
    assert row["turnkey_estimate_cents"] == cost
    assert row["turnkey_pricing"] == "fair_value"


def test_turnkey_place_without_market_uses_fair_value() -> None:
    world = bootstrap_frontier(seed=15)
    seed_world_blueprints(world)
    world.market_asks_by_material.clear()
    party = PartyId("player")
    pid = _unclaimed_land(world)
    claim_plot(world, party, pid)
    bp = world.blueprints["field_stockade"]
    need = compute_turnkey_cost_cents(world, bp)
    cash_acct = party_cash_account(party)
    from realm.core.ledger import system_reserve_account

    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=cash_acct,
        amount_cents=max(0, need - world.ledger.balance(cash_acct) + 1_000),
    )
    r = place_blueprint(world, party, pid, "field_stockade", 0, 0, build_mode="turnkey")
    assert r["ok"], r


def test_backward_compat_build_on_plot() -> None:
    world = bootstrap_frontier(seed=13)
    seed_world_blueprints(world)
    party = PartyId("player")
    pid = _unclaimed_land(world)
    claim_plot(world, party, pid)
    r = build_on_plot(world, party, pid, "field_stockade", build_mode="turnkey")
    assert r["ok"], r
    assert world.plot_buildings

"""Extraction recipes: subsurface gates + scaled primary outputs."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.production.buildings import build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.production import start_production
from realm.production.recipes import RECIPES
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
from realm.world import SubsurfaceRoll, bootstrap_frontier

from turnkey_fixtures import ensure_plot_grid_power, grant_turnkey_self_materials
from plot_helpers import claimable_land_plot_id, first_terrain_plot_id


def _advance_until_building_ready(w, party: PartyId, plot_id: PlotId, building_id: str) -> None:
    while True:
        row = next(
            (
                b
                for b in w.plot_buildings
                if b.get("party") == str(party)
                and b.get("plot_id") == str(plot_id)
                and b.get("building_id") == building_id
            ),
            None,
        )
        assert row is not None
        ct = row.get("completes_at_tick")
        if ct is None or w.tick >= int(ct):
            return
        advance_tick(w)


def _complete_recipe(w, recipe_id: str) -> None:
    for _ in range(RECIPES[recipe_id].duration_ticks):
        advance_tick(w)


def _turnkey(w, party: PartyId, pid: PlotId, building_id: str) -> None:
    grant_turnkey_self_materials(w, party, building_id)
    r = build_on_plot(w, party, pid, building_id, build_mode="self")
    assert r["ok"] is True, r


def test_mine_iron_rejected_when_subsurface_below_threshold() -> None:
    w = bootstrap_frontier(seed=9, grid_width=8, grid_height=4)
    player = PartyId("player")
    pid = first_terrain_plot_id(w, Terrain.MOUNTAIN)
    assert claim_plot(w, player, pid)["ok"] is True
    w.plots[pid].subsurface = SubsurfaceRoll(
        iron_ore_grade=0.2,
        copper_ore_grade=0.5,
        clay_grade=0.5,
        coal_grade=0.5,
    )
    assert survey_plot(w, player, pid)["ok"] is True
    _turnkey(w, player, pid, "strip_mine")
    _advance_until_building_ready(w, player, pid, "strip_mine")
    r = start_production(w, player, pid, "mine_iron_ore")
    assert r["ok"] is False
    assert r["reason"] == "subsurface below threshold for this recipe"


def test_mine_iron_completes_with_scaled_iron_ore_qty() -> None:
    w = bootstrap_frontier(seed=9, grid_width=8, grid_height=4)
    player = PartyId("player")
    pid = first_terrain_plot_id(w, Terrain.MOUNTAIN)
    assert claim_plot(w, player, pid)["ok"] is True
    w.plots[pid].subsurface = SubsurfaceRoll(
        iron_ore_grade=0.95,
        copper_ore_grade=0.5,
        clay_grade=0.5,
        coal_grade=0.5,
    )
    assert survey_plot(w, player, pid)["ok"] is True
    _turnkey(w, player, pid, "strip_mine")
    _advance_until_building_ready(w, player, pid, "strip_mine")
    ensure_plot_grid_power(w, pid)
    assert start_production(w, player, pid, "mine_iron_ore")["ok"] is True
    _complete_recipe(w, "mine_iron_ore")
    from realm.infrastructure.plot_logistics import plot_output_qty

    assert plot_output_qty(w, pid, MaterialId("iron_ore")) >= 2


def test_chop_timber_on_forest_plot() -> None:
    w = bootstrap_frontier(seed=1, grid_width=3, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    # Sprint 1: chop_timber is strict forest only — force the terrain after the claim.
    from realm.world.terrain import Terrain

    w.plots[pid].terrain = Terrain.FOREST
    assert survey_plot(w, player, pid)["ok"] is True
    _turnkey(w, player, pid, "timber_yard")
    _advance_until_building_ready(w, player, pid, "timber_yard")
    ensure_plot_grid_power(w, pid)
    assert start_production(w, player, pid, "chop_timber")["ok"] is True
    _complete_recipe(w, "chop_timber")
    assert w.inventory.qty(player, MaterialId("timber")) >= 2

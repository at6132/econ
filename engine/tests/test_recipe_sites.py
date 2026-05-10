"""Recipe site rules: catalog parity and terrain gating."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.ids import MaterialId, PartyId, PlotId
from realm.production import start_production
from realm.recipe_sites import (
    assert_recipe_site_catalog_complete,
    recipe_allowed_on_terrain,
    recipe_ids_for_surveyed_terrain,
)
from realm.terrain import Terrain
from realm.world import bootstrap_frontier


def test_recipe_sites_covers_all_recipes() -> None:
    assert_recipe_site_catalog_complete()


def test_steel_rejected_on_plains_even_when_surveyed() -> None:
    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    plot = w.plots[pid]
    assert plot.terrain == Terrain.PLAINS
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    assert recipe_allowed_on_terrain(plot.terrain, "steel_alloy") is False
    player = PartyId("player")
    w.inventory.add(player, MaterialId("iron_ingot"), 2)
    w.inventory.add(player, MaterialId("coal"), 2)
    w.inventory.add(player, MaterialId("electricity"), 2)
    r = start_production(w, player, pid, "steel_alloy")
    assert r["ok"] is False
    assert r["reason"] == "recipe not available on this plot"


def test_water_surveyed_plot_offers_no_recipe_ids() -> None:
    w = bootstrap_frontier(seed=7, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    assert w.plots[pid].terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP)
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    assert recipe_ids_for_surveyed_terrain(w.plots[pid].terrain, surveyed=True) == []


def test_mountain_includes_smelt_and_steel_not_sawmill() -> None:
    w = bootstrap_frontier(seed=9, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    p = w.plots[pid]
    assert p.terrain == Terrain.MOUNTAIN
    p.surveyed = True
    ids = recipe_ids_for_surveyed_terrain(p.terrain, surveyed=True)
    assert "smelt_iron" in ids and "steel_alloy" in ids and "sawmill" not in ids

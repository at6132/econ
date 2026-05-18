"""Recipe site rules + workshop equipment gating."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.production.buildings import build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.production import start_production
from realm.production.recipe_sites import assert_recipe_site_catalog_complete, recipe_allowed_on_terrain
from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
from realm.world import bootstrap_frontier

from turnkey_fixtures import grant_turnkey_self_materials
from plot_helpers import claimable_land_plot_id, first_land_plot_id, first_terrain_plot_id, first_water_plot_id


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


def test_recipe_sites_covers_all_recipes() -> None:
    assert_recipe_site_catalog_complete()


def test_sawmill_requires_wood_shop_on_plains() -> None:
    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    assert recipe_allowed_on_terrain(w.plots[pid].terrain, "sawmill") is True
    r = start_production(w, player, pid, "sawmill")
    assert r["ok"] is False
    assert r["reason"] == "missing workshop: wood_shop"


def test_sawmill_ok_after_turnkey_wood_shop() -> None:
    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    grant_turnkey_self_materials(w, player, "wood_shop")
    assert build_on_plot(w, player, pid, "wood_shop", build_mode="self")["ok"] is True
    _advance_until_building_ready(w, player, pid, "wood_shop")
    assert start_production(w, player, pid, "sawmill")["ok"] is True


def test_water_surveyed_plot_offers_no_recipe_ids() -> None:
    w = bootstrap_frontier(seed=7, grid_width=8, grid_height=4)
    pid = first_water_plot_id(w)
    plot = w.plots[pid]
    assert plot.terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP)
    assert claim_plot(w, PartyId("player"), pid)["ok"] is False
    plot.surveyed = True
    assert recipe_ids_on_plot_for_owner(w, plot) == []


def test_mountain_foundry_unlocks_smelt_in_recipe_ids() -> None:
    w = bootstrap_frontier(seed=9, grid_width=8, grid_height=4)
    pid = first_terrain_plot_id(w, Terrain.MOUNTAIN)
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    assert "smelt_iron" not in recipe_ids_on_plot_for_owner(w, w.plots[pid])
    grant_turnkey_self_materials(w, player, "foundry")
    assert build_on_plot(w, player, pid, "foundry", build_mode="self")["ok"] is True
    _advance_until_building_ready(w, player, pid, "foundry")
    ids = recipe_ids_on_plot_for_owner(w, w.plots[pid])
    assert "smelt_iron" in ids and "steel_alloy" in ids and "sawmill" not in ids

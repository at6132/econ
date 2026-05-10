"""Phase 2 recipe catalog: size targets and matter-balanced process chains."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.ids import MaterialId, PartyId, PlotId
from realm.materials import MATERIALS, all_material_ids
from realm.production import start_production
from realm.recipes import RECIPES
from realm.tick import advance_tick
from realm.world import bootstrap_frontier

# Recipes authored so sum(inputs) == sum(outputs) in inventory units (Law 1 friendly).
_PHASE2_UNIT_BALANCED = frozenset(
    {
        "mine_stone",
        "wash_sand",
        "crush_limestone",
        "lime_burn",
        "mortar_mix",
        "glass_blow",
        "steel_alloy",
        "wire_draw",
        "charcoal_burn",
        "pottery_kiln",
        "mill_flour",
        "bake_bread",
    }
)


def test_material_catalog_meets_phase2_target() -> None:
    assert len(MATERIALS) >= 25


def test_recipe_catalog_meets_phase2_target() -> None:
    assert len(RECIPES) >= 15


def test_phase2_recipes_conserve_inventory_unit_counts() -> None:
    for rid in _PHASE2_UNIT_BALANCED:
        r = RECIPES[rid]
        assert sum(r.inputs.values()) == sum(r.outputs.values()), rid


def _party_unit_total(w, party: PartyId) -> int:
    return sum(w.inventory.qty(party, mid) for mid in all_material_ids())


def test_mill_flour_run_conserves_player_inventory_units() -> None:
    w = bootstrap_frontier(seed=31, grid_width=3, grid_height=2)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    u0 = _party_unit_total(w, player)
    assert start_production(w, player, pid, "mill_flour")["ok"] is True
    for _ in range(3):
        advance_tick(w)
    assert _party_unit_total(w, player) == u0


def test_steel_alloy_outputs_match_inputs_units() -> None:
    w = bootstrap_frontier(seed=32, grid_width=3, grid_height=2)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    # Bootstrap already has smelt inputs; add one more iron ingot for a steel batch.
    w.inventory.add(player, MaterialId("iron_ingot"), 1)
    u0 = _party_unit_total(w, player)
    assert start_production(w, player, pid, "steel_alloy")["ok"] is True
    for _ in range(5):
        advance_tick(w)
    assert _party_unit_total(w, player) == u0

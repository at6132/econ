"""Research-unlocked recipes exist, run on grid, and honor efficiency bonuses."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.production.recipes import RECIPES
from realm.research.bonuses import research_output_multiplier
from realm.research.research_lab import complete_research
from realm.world import bootstrap_frontier


def _claim(w, party: PartyId) -> PlotId:
    for pid, plot in w.plots.items():
        if plot.owner is None and not str(plot.terrain.value).startswith("water"):
            pid = PlotId(str(pid))
            assert claim_plot(w, party, pid)["ok"] is True
            assert survey_plot(w, party, pid)["ok"] is True
            return pid
    raise AssertionError("no plot")


def test_all_tech_tree_recipes_exist_in_recipes() -> None:
    from realm.research.tech_tree import TECH_NODES

    for node in TECH_NODES.values():
        for rid in node["unlocks_recipes"]:
            assert rid in RECIPES, f"missing recipe {rid}"
            assert RECIPES[rid].requires_discovery is True


def test_turbine_generator_unlocked_after_steam_turbine_research() -> None:
    w = bootstrap_frontier(seed=401, grid_width=4, grid_height=3)
    player = PartyId("player")
    assert not w.can_party_run_recipe(player, "turbine_generator")
    complete_research(w, player, "electric_motors")
    complete_research(w, player, "steam_turbine")
    assert "turbine_generator" in w.party_recipe_books[str(player)]
    assert w.can_party_run_recipe(player, "turbine_generator")
    r = RECIPES["turbine_generator"]
    assert r.outputs[MaterialId("electricity")] == 5
    assert r.outputs[MaterialId("electricity")] > RECIPES["coal_generator"].outputs[MaterialId("electricity")]


def test_research_bonus_multiplies_output() -> None:
    w = bootstrap_frontier(seed=402, grid_width=2, grid_height=2)
    player = PartyId("player")
    w.scenario_state["research_bonuses"] = {str(player): {"mine_coal": 0.25}}
    assert research_output_multiplier(w, player, "mine_coal") == 1.25
    w.scenario_state["research_bonuses"][str(player)]["all"] = 0.1
    assert research_output_multiplier(w, player, "mine_coal") == 1.35

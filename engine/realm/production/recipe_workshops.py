"""Recipe ↔ workshop building (equipment on plot before production runs)."""

from __future__ import annotations

from realm.production.decay import building_effective_for_bonuses
from realm.core.ids import PartyId, PlotId
from realm.core.time_scale import building_operational
from realm.production.recipe_sites import (
    recipe_allowed_on_plot,
    recipe_allowed_on_terrain,
    subsurface_allows_recipe,
    terrain_allows_workshop,
)
from realm.production.recipes import RECIPES
from realm.world import Plot, World


def plot_has_workshop_for_recipe(world: World, party: PartyId, plot_id: PlotId, recipe_id: str) -> bool:
    """True if an effective (condition) building on this plot matches the recipe's workshop line."""
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return False
    if recipe.requires_tool is not None:
        return True
    req = recipe.requires_building_id
    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("plot_id") != str(plot_id):
            continue
        if b.get("building_id") != req:
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if not building_effective_for_bonuses(b):
            continue
        return True
    return False


def recipe_ids_on_plot_for_owner(world: World, plot: Plot) -> list[str]:
    """Surveyed dry plot owned by ``plot.owner``: recipes allowed by terrain (+ coastal),
    workshop, subsurface, and discovery."""
    if plot.owner is None or not plot.surveyed or not terrain_allows_workshop(plot.terrain):
        return []
    party = plot.owner
    out: list[str] = []
    for rid in RECIPES:
        recipe = RECIPES[rid]
        ok, _ = recipe_allowed_on_plot(world, plot, rid)
        if not ok:
            continue
        if not subsurface_allows_recipe(plot, recipe):
            continue
        if not world.can_party_run_recipe(party, rid):
            continue
        if recipe.requires_tool is not None:
            out.append(rid)
            continue
        if not plot_has_workshop_for_recipe(world, party, plot.plot_id, rid):
            continue
        out.append(rid)
    out.sort()
    return out

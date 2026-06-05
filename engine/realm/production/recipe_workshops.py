"""Recipe ↔ workshop building (equipment on plot before production runs)."""

from __future__ import annotations

from realm.production.decay import building_effective_for_bonuses
from realm.core.ids import PartyId, PlotId
from realm.core.time_scale import building_operational
from realm.production.recipe_sites import (
    recipe_allowed_on_plot,
    terrain_allows_workshop,
)
from realm.production.recipes import RECIPES
from realm.world import Plot, World


def _building_on_plot_enables_recipe(
    world: World, party: PartyId, plot_id: PlotId, recipe_id: str
) -> bool:
    """True when an operational building's blueprint lists ``recipe_id`` in ``enabled_recipe_ids``."""
    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("plot_id") != str(plot_id):
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if not building_effective_for_bonuses(b):
            continue
        bp_id = str(b.get("building_id") or b.get("blueprint_id") or "")
        bp = world.blueprints.get(bp_id)
        if bp is not None and recipe_id in bp.enabled_recipe_ids:
            return True
    return False


def plot_has_workshop_for_recipe(world: World, party: PartyId, plot_id: PlotId, recipe_id: str) -> bool:
    """True if an effective (condition) building on this plot matches the recipe's workshop line."""
    from realm.production.custom_content import get_recipe

    recipe = get_recipe(world, recipe_id)
    if recipe is None:
        return False
    if recipe.requires_tool is not None:
        return True
    req = recipe.requires_building_id
    if req:
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
    return _building_on_plot_enables_recipe(world, party, plot_id, recipe_id)


def _recipe_eligible_on_plot(
    world: World, plot: Plot, party: PartyId, recipe_id: str
) -> bool:
    from realm.production.custom_content import get_recipe
    from realm.production.recipe_sites import subsurface_allows_recipe

    recipe = get_recipe(world, recipe_id)
    if recipe is None:
        return False
    ok, _ = recipe_allowed_on_plot(world, plot, recipe_id)
    if not ok:
        return False
    if not subsurface_allows_recipe(plot, recipe):
        return False
    from realm.events.seasons import recipe_blocked_by_season

    blocked, _ = recipe_blocked_by_season(world, recipe_id, plot)
    if blocked:
        return False
    if not world.can_party_run_recipe(party, recipe_id):
        return False
    if recipe.requires_tool is not None:
        return True
    return plot_has_workshop_for_recipe(world, party, plot.plot_id, recipe_id)


def recipe_ids_on_plot_for_owner(world: World, plot: Plot) -> list[str]:
    """Surveyed dry plot owned by ``plot.owner``: recipes allowed by terrain (+ coastal),
    workshop, subsurface, and discovery."""
    if plot.owner is None or not plot.surveyed or not terrain_allows_workshop(plot.terrain):
        return []
    party = plot.owner
    out: list[str] = []
    seen: set[str] = set()
    for rid in RECIPES:
        if _recipe_eligible_on_plot(world, plot, party, rid):
            out.append(rid)
            seen.add(rid)
    from realm.production.custom_content import custom_recipes_store

    for rid in sorted(custom_recipes_store(world).keys()):
        if rid in seen:
            continue
        if _recipe_eligible_on_plot(world, plot, party, rid):
            out.append(rid)
            seen.add(rid)
    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("plot_id") != str(plot.plot_id):
            continue
        bp_id = str(b.get("building_id") or b.get("blueprint_id") or "")
        bp = world.blueprints.get(bp_id)
        if bp is None:
            continue
        for rid in bp.enabled_recipe_ids:
            if rid in seen:
                continue
            if _recipe_eligible_on_plot(world, plot, party, rid):
                out.append(rid)
                seen.add(rid)
    out.sort()
    return out

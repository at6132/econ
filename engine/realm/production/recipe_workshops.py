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
from realm.world.runtime_cache import bucket


def _tick_cache(world: World, key: str) -> dict:
    """Per-tick scratch dict in runtime cache (cleared when ``world.tick`` changes)."""
    root = bucket(world)
    slot = root.get(key)
    tick = int(world.tick)
    if not isinstance(slot, dict) or int(slot.get("tick", -1)) != tick:
        slot = {"tick": tick, "data": {}}
        root[key] = slot
    data = slot["data"]
    assert isinstance(data, dict)
    return data


def _buildings_on_plot(world: World, party: PartyId, plot_id: PlotId) -> list[dict]:
    cache = _tick_cache(world, "_rw_buildings_on_plot")
    key = (str(party), str(plot_id))
    if key not in cache:
        cache[key] = [
            b
            for b in world.plot_buildings
            if b.get("party") == str(party) and b.get("plot_id") == str(plot_id)
        ]
    return cache[key]


def _building_on_plot_enables_recipe(
    world: World, party: PartyId, plot_id: PlotId, recipe_id: str
) -> bool:
    """True when an operational building's blueprint lists ``recipe_id`` in ``enabled_recipe_ids``."""
    for b in _buildings_on_plot(world, party, plot_id):
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
    cache = _tick_cache(world, "_rw_plot_has_workshop")
    key = (str(party), str(plot_id), recipe_id)
    if key in cache:
        return bool(cache[key])

    from realm.production.custom_content import get_recipe

    recipe = get_recipe(world, recipe_id)
    if recipe is None:
        cache[key] = False
        return False
    if recipe.requires_tool is not None:
        cache[key] = True
        return True
    req = recipe.requires_building_id
    if req:
        for b in _buildings_on_plot(world, party, plot_id):
            if b.get("building_id") != req:
                continue
            if not building_operational(b, at_tick=world.tick):
                continue
            if not building_effective_for_bonuses(b):
                continue
            cache[key] = True
            return True
    result = _building_on_plot_enables_recipe(world, party, plot_id, recipe_id)
    cache[key] = result
    return result


def _recipe_eligible_on_plot(
    world: World, plot: Plot, party: PartyId, recipe_id: str
) -> bool:
    cache = _tick_cache(world, "_rw_recipe_eligible")
    key = (str(plot.plot_id), str(party), recipe_id)
    if key in cache:
        return bool(cache[key])

    from realm.production.custom_content import get_recipe
    from realm.production.recipe_sites import subsurface_allows_recipe

    recipe = get_recipe(world, recipe_id)
    if recipe is None:
        cache[key] = False
        return False
    ok, _ = recipe_allowed_on_plot(world, plot, recipe_id)
    if not ok:
        cache[key] = False
        return False
    if not subsurface_allows_recipe(plot, recipe):
        cache[key] = False
        return False
    from realm.events.seasons import recipe_blocked_by_season

    blocked, _ = recipe_blocked_by_season(world, recipe_id, plot)
    if blocked:
        cache[key] = False
        return False
    if not world.can_party_run_recipe(party, recipe_id):
        cache[key] = False
        return False
    if recipe.requires_tool is not None:
        cache[key] = True
        return True
    result = plot_has_workshop_for_recipe(world, party, plot.plot_id, recipe_id)
    cache[key] = result
    return result


def recipe_ids_on_plot_for_owner(world: World, plot: Plot) -> list[str]:
    """Surveyed dry plot owned by ``plot.owner``: recipes allowed by terrain (+ coastal),
    workshop, subsurface, and discovery."""
    if plot.owner is None or not plot.surveyed or not terrain_allows_workshop(plot.terrain):
        return []
    cache = _tick_cache(world, "_rw_recipe_ids_on_plot")
    plot_key = str(plot.plot_id)
    if plot_key in cache:
        return list(cache[plot_key])

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
    for b in _buildings_on_plot(world, party, plot.plot_id):
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
    cache[plot_key] = out
    return out

"""Which recipes may run on which plot terrain (solo gameplay — geography gates industry).

Water tiles have no workshop recipes. API lists eligible ids only for **surveyed** dry land;
``start_production`` also requires ``plot.surveyed`` (enforced in ``production.py``).
"""

from __future__ import annotations

from typing import Final

from realm.recipes import RECIPES, Recipe
from realm.terrain import Terrain
from realm.world import Plot

T = Terrain

# Every key in ``RECIPES`` must appear here (see ``test_recipe_sites_covers_all_recipes``).
RECIPE_ALLOWED_TERRAINS: Final[dict[str, frozenset[Terrain]]] = {
    "sawmill": frozenset({T.FOREST, T.PLAINS}),
    "twist_rope": frozenset({T.FOREST, T.PLAINS, T.SWAMP, T.TUNDRA}),
    "build_ladder": frozenset({T.FOREST, T.PLAINS, T.MOUNTAIN}),
    "smelt_iron": frozenset({T.MOUNTAIN}),
    "smelt_copper": frozenset({T.MOUNTAIN}),
    "coal_generator": frozenset(
        {T.PLAINS, T.FOREST, T.MOUNTAIN, T.DESERT, T.TUNDRA, T.SWAMP}
    ),
    "kiln_brick": frozenset({T.PLAINS, T.DESERT, T.SWAMP}),
    "mine_stone": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS}),
    "wash_sand": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS}),
    "crush_limestone": frozenset({T.MOUNTAIN, T.DESERT}),
    "lime_burn": frozenset({T.MOUNTAIN, T.DESERT}),
    "mortar_mix": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS}),
    "glass_blow": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS}),
    "steel_alloy": frozenset({T.MOUNTAIN}),
    "wire_draw": frozenset({T.MOUNTAIN, T.PLAINS}),
    "charcoal_burn": frozenset({T.FOREST, T.PLAINS, T.MOUNTAIN, T.TUNDRA}),
    "pottery_kiln": frozenset({T.PLAINS, T.SWAMP, T.DESERT}),
    "mill_flour": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA}),
    "bake_bread": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA}),
    "mine_iron_ore": frozenset({T.MOUNTAIN}),
    "mine_copper_ore": frozenset({T.MOUNTAIN}),
    "mine_coal": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS, T.FOREST}),
    "dig_clay": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA}),
    "chop_timber": frozenset({T.FOREST, T.PLAINS}),
    "grow_grain": frozenset({T.PLAINS}),
    "hand_chop": frozenset({T.FOREST, T.PLAINS}),
    "hand_mine_coal": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS, T.FOREST}),
    "hand_mine_ore": frozenset({T.MOUNTAIN}),
    "hand_dig_clay": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA}),
}

_WATER: Final[frozenset[Terrain]] = frozenset({T.WATER_SHALLOW, T.WATER_DEEP})


def terrain_allows_workshop(terrain: Terrain) -> bool:
    """False on deep/shallow water (no fixed structures in this slice)."""
    return terrain not in _WATER


def subsurface_allows_recipe(plot: Plot, recipe: Recipe) -> bool:
    """Surveyed plot subsurface must meet recipe gates (extraction recipes)."""
    if not recipe.requires_subsurface:
        return True
    if not plot.surveyed:
        return False
    for field, mn in recipe.requires_subsurface:
        if float(getattr(plot.subsurface, field, 0.0)) < float(mn):
            return False
    return True


def recipe_allowed_on_terrain(terrain: Terrain, recipe_id: str) -> bool:
    if not terrain_allows_workshop(terrain):
        return False
    terrains = RECIPE_ALLOWED_TERRAINS.get(recipe_id)
    if terrains is None:
        return False
    return terrain in terrains


def recipe_ids_for_surveyed_terrain(terrain: Terrain, *, surveyed: bool) -> list[str]:
    """Sorted recipe ids for API on a surveyed plot (empty if unsurveyed or water)."""
    if not surveyed or not terrain_allows_workshop(terrain):
        return []
    out = [rid for rid in RECIPE_ALLOWED_TERRAINS if terrain in RECIPE_ALLOWED_TERRAINS[rid]]
    out.sort()
    return out


def assert_recipe_site_catalog_complete() -> None:
    """Call from tests — every authored recipe must declare allowed terrains."""
    missing = [rid for rid in RECIPES if rid not in RECIPE_ALLOWED_TERRAINS]
    extra = [rid for rid in RECIPE_ALLOWED_TERRAINS if rid not in RECIPES]
    if missing or extra:
        raise AssertionError(f"recipe_sites out of sync: missing={missing!r} extra={extra!r}")

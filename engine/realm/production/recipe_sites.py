"""Which recipes may run on which plot terrain (solo gameplay — geography gates industry).

Water tiles have no workshop recipes. API lists eligible ids only for **surveyed** dry land;
``start_production`` also requires ``plot.surveyed`` (enforced in ``production.py``).

In addition to the hard terrain gate, ``RECIPE_TERRAIN_BONUS_BPS`` carries per-terrain
**efficiency modifiers** (basis points, 10_000 = no change). Production scales final
output by this factor on completion — fertile valleys yield more grain, mountain seams
yield richer ore. Bonus terrains must also appear in ``RECIPE_ALLOWED_TERRAINS`` for the
recipe to even start.

Note: the engine's ``Terrain`` enum has 8 values (plains, forest, mountain, desert,
tundra, swamp, water_shallow, water_deep) — no separate ``coastal``/``valley``/``hills``.
Coastal-only recipes (fishing) use ``plot_is_coastal`` to detect plots adjacent to
water tiles, since coast is a *position* concept rather than a terrain class here.
"""

from __future__ import annotations

from typing import Final

from realm.production.recipes import RECIPES, Recipe
from realm.world.terrain import Terrain
from realm.world import Plot

T = Terrain

# Every key in ``RECIPES`` must appear here (see ``test_recipe_sites_covers_all_recipes``).
# Sprint 1: agricultural recipes are strict plains-only; forestry is forest-only; mining is
# any non-water land. Sprint 1 also adds fishing (coastal — see ``recipe_allowed_on_plot``).
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
    "mine_stone": frozenset({T.MOUNTAIN, T.PLAINS, T.TUNDRA}),
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
    # Sprint 1: ``mine_coal`` is land-only (no water tiles). Mountain/desert/plains/forest
    # already excluded water by virtue of the terrain enum; explicit list documents intent.
    "mine_coal": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS, T.FOREST, T.TUNDRA}),
    "dig_clay": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA}),
    # Sprint 1: ``chop_timber`` is forest only — no logging on grass plains.
    "chop_timber": frozenset({T.FOREST}),
    # Sprint 1: ``grow_grain`` strictly plains. Forest/swamp/tundra/desert all blocked.
    "grow_grain": frozenset({T.PLAINS}),
    "hand_chop": frozenset({T.FOREST}),
    "hand_mine_coal": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS, T.FOREST, T.TUNDRA}),
    "hand_mine_ore": frozenset({T.MOUNTAIN}),
    "hand_dig_clay": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA}),
    # Sprint 1 — coastal-only food source (see ``recipe_allowed_on_plot``). Terrain set
    # lists land terrains that *can* be coastal-adjacent so the API surfaces it on those
    # plot tiles; ``plot_is_coastal`` enforces the actual gate at production time.
    "fishing": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA, T.DESERT, T.MOUNTAIN}),
    # Sprint 3 — Phase D.1: smoking is a wood_shop process (land workshops).
    "smoke_fish": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA, T.DESERT, T.MOUNTAIN}),
    # Sprint 3 — Phase D.4: tidal power is coastal-only (gate enforced via
    # ``COASTAL_ONLY_RECIPES`` + ``plot_is_coastal``); the terrain envelope
    # lists land terrains that *can* be coastal-adjacent so the API surfaces it.
    "tidal_power": frozenset({T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA, T.DESERT, T.MOUNTAIN}),
    # Tier-2 extraction terrain envelopes (sulfur thrives in swamp+tundra mountain-fringe; silica is wide).
    "mine_sulfur_ore": frozenset({T.SWAMP, T.TUNDRA, T.MOUNTAIN, T.PLAINS}),
    "mine_saltpeter": frozenset({T.DESERT, T.PLAINS}),
    "mine_tin_ore": frozenset({T.MOUNTAIN, T.PLAINS}),
    "mine_lead_ore": frozenset({T.MOUNTAIN}),
    "mine_phosphate": frozenset({T.PLAINS, T.FOREST}),
    "mine_raw_silica": frozenset({T.DESERT, T.PLAINS, T.MOUNTAIN}),
    "hand_mine_sulfur": frozenset({T.SWAMP, T.TUNDRA, T.MOUNTAIN, T.PLAINS}),
    "hand_mine_tin": frozenset({T.MOUNTAIN, T.PLAINS}),
    # Tier-2 processing (chemical works tolerates plains/desert/mountain; foundry/stone_works inherit Tier-1 terrains).
    "refine_sulfur": frozenset({T.PLAINS, T.DESERT, T.MOUNTAIN, T.SWAMP}),
    "make_sulfuric_acid": frozenset({T.PLAINS, T.DESERT, T.MOUNTAIN, T.SWAMP}),
    "refine_saltpeter": frozenset({T.PLAINS, T.DESERT, T.MOUNTAIN}),
    "make_gunpowder": frozenset({T.PLAINS, T.DESERT, T.MOUNTAIN}),
    "smelt_tin": frozenset({T.MOUNTAIN}),
    "make_bronze": frozenset({T.MOUNTAIN}),
    "smelt_lead": frozenset({T.MOUNTAIN}),
    "process_phosphate": frozenset({T.PLAINS, T.DESERT, T.MOUNTAIN, T.SWAMP}),
    "fuse_silica": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS}),
    # Pig iron / cast iron — blast furnace + foundry country.
    "smelt_pig_iron": frozenset({T.MOUNTAIN}),
    "cast_iron_pour": frozenset({T.MOUNTAIN}),
    # Forge press + machine shop + tool workshop — heavy industry, mostly mountain & plains.
    "forge_pick_head": frozenset({T.MOUNTAIN, T.PLAINS}),
    "forge_saw_blade": frozenset({T.MOUNTAIN, T.PLAINS}),
    "forge_drill_bit": frozenset({T.MOUNTAIN, T.PLAINS}),
    "make_pump_unit": frozenset({T.MOUNTAIN, T.PLAINS}),
    "make_gear_set": frozenset({T.MOUNTAIN, T.PLAINS}),
    "assemble_mining_pick": frozenset({T.MOUNTAIN, T.PLAINS, T.FOREST}),
    "assemble_hand_saw": frozenset({T.MOUNTAIN, T.PLAINS, T.FOREST}),
    "assemble_pick_axe": frozenset({T.MOUNTAIN, T.PLAINS, T.FOREST}),
    # Tier-3 extraction & refining (drill rig + downstream foundry/chemical_works).
    "mine_platinum": frozenset({T.MOUNTAIN, T.DESERT, T.PLAINS, T.TUNDRA}),
    "mine_oil_shale": frozenset({T.SWAMP, T.PLAINS, T.MOUNTAIN, T.FOREST, T.TUNDRA}),
    "mine_rare_earth": frozenset({T.MOUNTAIN, T.DESERT, T.TUNDRA}),
    "refine_platinum": frozenset({T.MOUNTAIN}),
    "process_shale": frozenset({T.PLAINS, T.DESERT, T.MOUNTAIN, T.SWAMP}),
    # Phase 8C — herbalism + apothecary chain.
    "gather_herbs": frozenset({T.FOREST}),
    "make_medicine": frozenset({T.PLAINS, T.FOREST, T.MOUNTAIN, T.SWAMP, T.TUNDRA, T.DESERT}),
    # Soil remediation — same dry-land envelope as mining-adjacent ag degradation.
    "soil_remediation": frozenset({T.PLAINS, T.HILLS, T.SWAMP, T.TUNDRA, T.DESERT}),
    # Phase 9A — shipyard (coastal-only; same plot_is_coastal gate as the dock).
    # Terrain envelope mirrors tidal_power: any land-terrain that *can* be
    # water-adjacent is surfaced; ``COASTAL_ONLY_RECIPES`` enforces the actual
    # water-adjacency check at production start.
    "build_cargo_vessel": frozenset(
        {T.PLAINS, T.FOREST, T.SWAMP, T.TUNDRA, T.DESERT, T.MOUNTAIN}
    ),
}

_WATER: Final[frozenset[Terrain]] = frozenset({T.WATER_SHALLOW, T.WATER_DEEP})

# Per-recipe terrain efficiency overrides. 10_000 = no change. Production output is
# scaled by this factor AFTER the maintenance-efficiency multiplier so a degraded
# mountain mine still gets the mountain ore bonus on whatever it produces.
RECIPE_TERRAIN_BONUS_BPS: Final[dict[str, dict[Terrain, int]]] = {
    "mine_iron_ore": {T.MOUNTAIN: 12_000},   # 120% on mountains — richer seams
    "hand_mine_ore": {T.MOUNTAIN: 12_000},
    "mine_coal":     {T.MOUNTAIN: 11_000},   # 110% on mountains — coal beds run thicker
    "hand_mine_coal": {T.MOUNTAIN: 11_000},
}

# Recipes that only run on a coastal plot (water-adjacent land). Enforced by
# ``recipe_allowed_on_plot``; ``recipe_allowed_on_terrain`` is permissive so the
# API and UI can still surface the recipe on potentially-coastal terrains, with
# the plot-level check rejecting inland tries at production start.
COASTAL_ONLY_RECIPES: Final[frozenset[str]] = frozenset(
    {"fishing", "tidal_power", "build_cargo_vessel"}
)


def terrain_allows_workshop(terrain: Terrain) -> bool:
    """False on deep/shallow water (no fixed structures in this slice)."""
    return terrain not in _WATER


def plot_allows_structure(plot: Plot) -> bool:
    """Dry land only — residences, workshops, and claims require this."""
    return terrain_allows_workshop(plot.terrain)


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


def _world_cell_is_water(world, x: int, y: int) -> bool:
    """True when ``(x, y)`` is off-map, unclaimed, or a water terrain tile."""
    from realm.core.ids import PlotId
    from realm.world.plot_parcels import build_world_cell_index

    idx = world.scenario_state.get("world_cell_to_plot")
    if not isinstance(idx, dict) or not idx:
        idx = build_world_cell_index(world.plots)
    owner = idx.get(f"{x},{y}")
    if owner is None:
        return True
    wp = world.plots.get(PlotId(str(owner)))
    if wp is None:
        return True
    return wp.terrain in _WATER


def plot_is_coastal(world, plot: Plot) -> bool:
    """True when any world tile in the deed borders water or the map edge.

    Uses the full ``world_cells`` polyomino (not just the anchor ``x,y``), so
    multi-tile coastal parcels classify correctly for docks, fishing, and routes.
    """
    return bool(waterfront_build_cells(world, plot))


def waterfront_build_cells(world, plot: Plot) -> frozenset[tuple[int, int]]:
    """10m build-grid cells on this deed with a world-tile neighbour that is water.

    Used to gate dock / shipyard placement: the footprint must overlap at least one
    of these cells so a large coastal parcel cannot host a dock entirely inland.
    """
    if not plot_allows_structure(plot):
        return frozenset()
    from realm.world.plot_scale import (
        CELLS_PER_WORLD_TILE,
        plot_deed_grid_cells,
        plot_world_span,
    )

    min_x, min_y, _, _ = plot_world_span(plot)
    out: set[tuple[int, int]] = set()
    for cx, cy in plot_deed_grid_cells(plot):
        wx = min_x + cx // CELLS_PER_WORLD_TILE
        wy = min_y + cy // CELLS_PER_WORLD_TILE
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if _world_cell_is_water(world, wx + ddx, wy + ddy):
                out.add((cx, cy))
                break
    return frozenset(out)


def footprint_borders_water(
    world,
    plot: Plot,
    grid_x: int,
    grid_y: int,
    footprint_w: int,
    footprint_h: int,
) -> bool:
    """True when at least one cell of the footprint sits on the deed's waterfront."""
    front = waterfront_build_cells(world, plot)
    if not front:
        return False
    for dx in range(int(footprint_w)):
        for dy in range(int(footprint_h)):
            if (int(grid_x) + dx, int(grid_y) + dy) in front:
                return True
    return False


def recipe_allowed_on_plot(world, plot: Plot, recipe_id: str) -> tuple[bool, str | None]:
    """Strict plot-level gate. Returns ``(ok, reason)``.

    Adds the coastal check on top of ``recipe_allowed_on_terrain``: coastal-only
    recipes reject any dry plot that does not border a water tile.
    """
    if not recipe_allowed_on_terrain(plot.terrain, recipe_id):
        return (False, f"recipe not available on {plot.terrain.value} terrain")
    if recipe_id in COASTAL_ONLY_RECIPES and not plot_is_coastal(world, plot):
        return (False, f"{recipe_id} requires a coastal plot (adjacent to water)")
    return (True, None)


def recipe_terrain_bonus_bps(recipe_id: str, terrain: Terrain) -> int:
    """Per-recipe per-terrain output modifier (basis points; 10_000 = no change)."""
    table = RECIPE_TERRAIN_BONUS_BPS.get(recipe_id)
    if table is None:
        return 10_000
    return int(table.get(terrain, 10_000))


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

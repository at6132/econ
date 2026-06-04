"""Per-world-generation caches for waterfront scans and plot valuation.

Hot paths (settler claim scans, ``recipe_ids_on_plot_for_owner``, claim fees)
reuse results within a tick. ``invalidate_plot_geom_caches`` bumps the
generation when plot ownership changes so neighbor-waterfront geometry stays
correct.
"""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.world import Plot, World

_gen: dict[int, int] = {}
_waterfront: dict[tuple[int, int, PlotId], frozenset[tuple[int, int]]] = {}
_min_town: dict[tuple[int, int, PlotId], float] = {}
_plot_value: dict[tuple[int, int, PlotId], int] = {}
# Whole-world coastal classification, keyed by (id(world.plots), generation).
# One cheap O(world-cells) batch replaces ~N cold per-plot waterfront scans
# during a full map/world serialization (the cold path that made the first
# ``GET /world/map`` after a load take tens of seconds on Genesis).
_coastal: dict[tuple[int, int], frozenset[PlotId]] = {}

_PRUNE_AT = 12_000


def invalidate_plot_geom_caches() -> None:
    """Call when plot ownership or coastal adjacency may change (e.g. ``claim_plot``)."""
    for plots_id in list(_gen.keys()):
        _gen[plots_id] = int(_gen.get(plots_id, 0)) + 1
    if len(_waterfront) > _PRUNE_AT:
        _waterfront.clear()
        _min_town.clear()
        _plot_value.clear()
    # The coastal map is keyed by generation, so stale entries are never read,
    # but bound its growth alongside the other caches.
    if len(_coastal) > 64:
        _coastal.clear()


def _cache_key(world: World, plot_id: PlotId) -> tuple[int, int, PlotId]:
    plots_id = id(world.plots)
    gen = int(_gen.setdefault(plots_id, 0))
    return plots_id, gen, plot_id


def cached_waterfront_build_cells(
    world: World, plot: Plot
) -> frozenset[tuple[int, int]]:
    key = _cache_key(world, plot.plot_id)
    hit = _waterfront.get(key)
    if hit is not None:
        return hit
    from realm.production.recipe_sites import waterfront_build_cells_uncached

    val = waterfront_build_cells_uncached(world, plot)
    _waterfront[key] = val
    return val


def cached_min_town_distance(world: World, plot: Plot) -> float:
    key = _cache_key(world, plot.plot_id)
    hit = _min_town.get(key)
    if hit is not None:
        return hit
    val = _min_town_distance_uncached(world, plot)
    _min_town[key] = val
    return val


def cached_compute_plot_value(world: World, plot_id: PlotId) -> int:
    key = _cache_key(world, plot_id)
    hit = _plot_value.get(key)
    if hit is not None:
        return hit
    val = _compute_plot_value_uncached(world, plot_id)
    _plot_value[key] = val
    return val


def cached_coastal_plot_ids(world: World) -> frozenset[PlotId]:
    """Set of plot ids that are coastal, computed once per world generation.

    Equivalent to ``bool(waterfront_build_cells(world, plot))`` for every plot,
    but evaluated in a single O(world-cells) pass instead of a cold per-plot
    deed-grid scan. A dry plot is coastal iff one of its world tiles has a
    4-neighbour world tile that is water, unclaimed, or off-map — exactly the
    condition ``waterfront_build_cells_uncached`` tests (water plots return an
    empty set there, so they are never coastal).
    """
    plots_id = id(world.plots)
    gen = int(_gen.setdefault(plots_id, 0))
    key = (plots_id, gen)
    hit = _coastal.get(key)
    if hit is not None:
        return hit
    val = _compute_coastal_plot_ids(world)
    _coastal[key] = val
    return val


def _compute_coastal_plot_ids(world: World) -> frozenset[PlotId]:
    from realm.production.recipe_sites import _WATER
    from realm.world.plot_parcels import build_world_cell_index

    idx = world.scenario_state.get("world_cell_to_plot")
    if not isinstance(idx, dict) or not idx:
        idx = build_world_cell_index(world.plots)

    plots = world.plots
    # ``dry_tiles`` holds every world tile that is present AND not water. A
    # neighbour tile counts as "water" exactly when it is NOT in this set
    # (covers off-map, unclaimed, missing-plot, and water terrain — matching
    # ``_world_cell_is_water``).
    dry_tiles: set[tuple[int, int]] = set()
    cells_by_plot: dict[str, list[tuple[int, int]]] = {}
    for cell_key, owner in idx.items():
        owner_s = str(owner)
        wp = plots.get(PlotId(owner_s))
        if wp is None:
            continue
        sx, _, sy = str(cell_key).partition(",")
        try:
            x = int(sx)
            y = int(sy)
        except ValueError:
            continue
        cells_by_plot.setdefault(owner_s, []).append((x, y))
        if wp.terrain not in _WATER:
            dry_tiles.add((x, y))

    coastal: set[PlotId] = set()
    for owner_s, cells in cells_by_plot.items():
        wp = plots.get(PlotId(owner_s))
        if wp is None or wp.terrain in _WATER:
            continue  # water plots disallow structures → never coastal
        is_coastal = False
        for (x, y) in cells:
            if (
                (x + 1, y) not in dry_tiles
                or (x - 1, y) not in dry_tiles
                or (x, y + 1) not in dry_tiles
                or (x, y - 1) not in dry_tiles
            ):
                is_coastal = True
                break
        if is_coastal:
            coastal.add(PlotId(owner_s))
    return frozenset(coastal)


def _min_town_distance_uncached(world: World, plot: Plot) -> float:
    min_d = 9999.0
    px = int(plot.x)
    py = int(plot.y)
    for town in world.towns.values():
        cx = int(getattr(town, "center_x", 0))
        cy = int(getattr(town, "center_y", 0))
        d = abs(px - cx) + abs(py - cy)
        min_d = min(min_d, float(d))
    return min_d


def _compute_plot_value_uncached(world: World, plot_id: PlotId) -> int:
    from realm.world.real_estate import BASE_PLOT_VALUE_CENTS, MINERAL_VALUE_WEIGHTS

    plot = world.plots.get(plot_id)
    if plot is None:
        return 0
    terr = plot.terrain.value
    if terr.startswith("water"):
        return 0

    from realm.world.plot_scale import plot_world_tile_count

    value = BASE_PLOT_VALUE_CENTS * max(1, plot_world_tile_count(plot))
    min_town_dist = cached_min_town_distance(world, plot)
    if min_town_dist < 5:
        value = int(value * 3.5)
    elif min_town_dist < 10:
        value = int(value * 2.0)
    elif min_town_dist < 20:
        value = int(value * 1.4)

    if cached_waterfront_build_cells(world, plot):
        value = int(value * 1.5)

    sub = plot.subsurface
    for grade_attr, weight in MINERAL_VALUE_WEIGHTS.items():
        grade = float(getattr(sub, grade_attr, 0.0))
        value += int(grade * weight)

    demand = float(
        (world.scenario_state.get("plot_demand_scores") or {}).get(str(plot_id), 0.0)
    )
    value = int(value * (1.0 + demand * 0.5))
    return value

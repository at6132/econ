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

_PRUNE_AT = 12_000


def invalidate_plot_geom_caches() -> None:
    """Call when plot ownership or coastal adjacency may change (e.g. ``claim_plot``)."""
    for plots_id in list(_gen.keys()):
        _gen[plots_id] = int(_gen.get(plots_id, 0)) + 1
    if len(_waterfront) > _PRUNE_AT:
        _waterfront.clear()
        _min_town.clear()
        _plot_value.clear()


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

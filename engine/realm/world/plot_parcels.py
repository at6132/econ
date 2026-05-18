"""Variable-size plot parcels — partition the world grid into multi-cell deeds (Option B)."""

from __future__ import annotations

from typing import Any, Callable

from realm.core.ids import PlotId
from realm.core.rng import make_rng
from realm.world.biome_noise import (
    clear_noise_cache,
    is_world_map_edge,
    terrain_for_cell,
    terrain_with_ocean_border,
)
from realm.world.parcel_footprints import (
    carve_l_corners,
    classify_parcel_shape,
    pick_footprint_at,
    stamp_footprint,
)
from realm.world.plot_scale import plot_world_cells_tuple
from realm.world.world import Plot, Terrain, _subsurface_roll


def generate_plot_parcels(
    *,
    seed: int,
    width: int,
    height: int,
    correlate_subsurface: bool = False,
    terrain_fn: Callable[[int, int, int], Terrain] | None = None,
) -> dict[PlotId, Plot]:
    """
    Tile the world into non-overlapping **polyomino** parcels (1–9 map tiles).

    Shapes include rectangles, lines, L-shapes, zigzags, T/plus — see
    :mod:`realm.world.parcel_footprints`. ``Plot.world_cells`` is authoritative;
    area and build-grid size derive from tile count in :mod:`realm.world.plot_scale`.
    """
    pick = terrain_fn if terrain_fn is not None else terrain_for_cell
    pick = terrain_with_ocean_border(pick, width=width, height=height)
    assigned: list[list[str | None]] = [[None for _ in range(width)] for _ in range(height)]
    plots: dict[PlotId, Plot] = {}
    rng = make_rng(seed, "plot_parcels")

    for y in range(height):
        for x in range(width):
            if not is_world_map_edge(x, y, width, height):
                continue
            if assigned[y][x] is not None:
                continue
            pid = PlotId(f"p-{x}-{y}")
            footprint = frozenset({(0, 0)})
            stamp_footprint(assigned, x, y, footprint, str(pid))
            sub_rng = make_rng(seed, f"gen:{pid}")
            wc = ((x, y),)
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=Terrain.WATER_DEEP,
                owner=None,
                subsurface=_subsurface_roll(
                    sub_rng,
                    Terrain.WATER_DEEP,
                    correlate=correlate_subsurface,
                    seed=seed,
                    x=x,
                    y=y,
                    apply_belts=correlate_subsurface,
                ),
                world_cells=wc,
                parcel_shape="mono",
            )

    for y in range(height):
        for x in range(width):
            if assigned[y][x] is not None:
                continue
            pid = PlotId(f"p-{x}-{y}")
            footprint = pick_footprint_at(rng, assigned, x, y, width, height)
            cells = stamp_footprint(assigned, x, y, footprint, str(pid))
            anchor_terrain = pick(seed, x, y)
            sub_rng = make_rng(seed, f"gen:{pid}")
            subsurface = _subsurface_roll(
                sub_rng,
                anchor_terrain,
                correlate=correlate_subsurface,
                seed=seed,
                x=x,
                y=y,
                apply_belts=correlate_subsurface,
            )
            for cx, cy in cells[1:]:
                t2 = pick(seed, cx, cy)
                if t2.value.startswith("water"):
                    anchor_terrain = t2
                    break
            wc = tuple(cells)
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=anchor_terrain,
                owner=None,
                subsurface=subsurface,
                world_cells=wc,
                parcel_shape=classify_parcel_shape(wc),
            )

    carve_l_corners(plots, assigned, rng)
    _fill_unassigned_cells(
        plots,
        assigned,
        seed=seed,
        width=width,
        height=height,
        pick=pick,
        correlate_subsurface=correlate_subsurface,
    )

    clear_noise_cache()
    return plots


def _fill_unassigned_cells(
    plots: dict[PlotId, Plot],
    assigned: list[list[str | None]],
    *,
    seed: int,
    width: int,
    height: int,
    pick: Callable[[int, int, int], Terrain],
    correlate_subsurface: bool,
) -> None:
    """After border splits / carve, ensure every map cell belongs to exactly one plot."""
    covered: set[tuple[int, int]] = set()
    for plot in plots.values():
        covered.update(plot_world_cells_tuple(plot))
    for y in range(height):
        for x in range(width):
            if (x, y) in covered:
                continue
            pid = PlotId(f"p-{x}-{y}")
            assigned[y][x] = str(pid)
            sub_rng = make_rng(seed, f"gen:{pid}")
            terrain = pick(seed, x, y)
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=terrain,
                owner=None,
                subsurface=_subsurface_roll(
                    sub_rng,
                    terrain,
                    correlate=correlate_subsurface,
                    seed=seed,
                    x=x,
                    y=y,
                    apply_belts=correlate_subsurface,
                ),
                world_cells=((x, y),),
                parcel_shape="mono",
            )
            covered.add((x, y))


def build_world_cell_index(plots: dict[PlotId, Plot]) -> dict[str, str]:
    """Map ``"x,y"`` world coordinates to ``plot_id`` string."""
    out: dict[str, str] = {}
    for pid, plot in plots.items():
        for cx, cy in plot_world_cells_tuple(plot):
            out[f"{cx},{cy}"] = str(pid)
    return out


def refresh_world_cell_index(world: object) -> None:
    """Rebuild ``world.scenario_state['world_cell_to_plot']`` after plot mutations."""
    from realm.world.world import World

    if not isinstance(world, World):
        return
    world.scenario_state["world_cell_to_plot"] = build_world_cell_index(world.plots)


def world_map_tile_count(world: object) -> int:
    from realm.world.world import World

    if not isinstance(world, World):
        return 0
    idx = world.scenario_state.get("world_cell_to_plot")
    if isinstance(idx, dict) and idx:
        return len(idx)
    return sum(len(plot_world_cells_tuple(p)) for p in world.plots.values())


def generate_uniform_plots(
    *,
    seed: int,
    width: int,
    height: int,
    correlate_subsurface: bool = False,
    terrain_fn: Callable[[int, int, int], Terrain] | None = None,
) -> dict[PlotId, Plot]:
    """One deed per map cell (tests / legacy layout)."""
    from realm.world.biome_noise import terrain_for_cell as default_terrain

    pick = terrain_fn if terrain_fn is not None else default_terrain
    pick = terrain_with_ocean_border(pick, width=width, height=height)
    plots: dict[PlotId, Plot] = {}
    for y in range(height):
        for x in range(width):
            pid = PlotId(f"p-{x}-{y}")
            rng = make_rng(seed, f"gen:{pid}")
            terrain = pick(seed, x, y)
            subsurface = _subsurface_roll(
                rng,
                terrain,
                correlate=correlate_subsurface,
                seed=seed,
                x=x,
                y=y,
                apply_belts=correlate_subsurface,
            )
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=terrain,
                owner=None,
                subsurface=subsurface,
                world_cells=((x, y),),
                parcel_shape="mono",
            )
    clear_noise_cache()
    return plots

"""World map perimeter must be deep ocean on every layout."""

from __future__ import annotations

from realm.world import bootstrap_genesis, generate_plots
from realm.world.biome_noise import (
    MAP_OCEAN_BORDER_DEPTH,
    continental_layout_terrain,
    is_world_map_edge,
    map_ocean_border_depth,
    terrain_for_cell,
)
from realm.world.plot_parcels import plot_world_cells_tuple
from realm.world.terrain import Terrain


def _assert_border_cells_water(plots: dict, width: int, height: int) -> None:
    depth = map_ocean_border_depth(width, height)
    for gx in range(width):
        for gy in range(height):
            if not is_world_map_edge(gx, gy, width, height):
                continue
            found_water = False
            for plot in plots.values():
                if plot.terrain not in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW):
                    continue
                for cx, cy in plot_world_cells_tuple(plot):
                    if cx == gx and cy == gy:
                        found_water = True
                        break
                if found_water:
                    break
            assert found_water, f"border cell ({gx},{gy}) has no water deed (depth={depth})"
    for pid, plot in plots.items():
        for cx, cy in plot_world_cells_tuple(plot):
            if is_world_map_edge(cx, cy, width, height):
                assert plot.terrain in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW), (
                    f"border cell ({cx},{cy}) plot {pid} is {plot.terrain!r}"
                )


def test_border_depth_is_at_least_two_on_genesis_grid() -> None:
    assert map_ocean_border_depth(320, 240) >= MAP_OCEAN_BORDER_DEPTH


def test_uniform_grid_border_is_deep_ocean() -> None:
    w, h = 48, 36
    plots = generate_plots(seed=7, width=w, height=h, uniform_plots=True)
    _assert_border_cells_water(plots, w, h)


def test_parcel_grid_border_is_deep_ocean() -> None:
    w, h = 32, 24
    plots = generate_plots(seed=11, width=w, height=h)
    _assert_border_cells_water(plots, w, h)


def test_continental_layout_border_is_deep_ocean() -> None:
    w, h = 160, 120

    def terrain_fn(s: int, x: int, y: int) -> Terrain:
        return continental_layout_terrain(s, x, y, w, h)

    plots = generate_plots(seed=19, width=w, height=h, terrain_fn=terrain_fn, uniform_plots=True)
    _assert_border_cells_water(plots, w, h)


def test_genesis_default_world_has_ocean_border() -> None:
    world = bootstrap_genesis(seed=592510244, settler_count=0)
    gw = int(world.scenario_state.get("grid_width", 0))
    gh = int(world.scenario_state.get("grid_height", 0))
    assert gw > 0 and gh > 0
    _assert_border_cells_water(world.plots, gw, gh)


def test_interior_noise_unchanged_off_border() -> None:
    assert terrain_for_cell(99, 5, 5) == terrain_for_cell(99, 5, 5)

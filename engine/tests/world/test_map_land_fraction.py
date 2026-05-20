"""Continental worldgen: at least half the map is solid land; edges are not forced ocean."""

from __future__ import annotations

from realm.world import bootstrap_genesis, generate_plots
from realm.world.biome_noise import (
    GENESIS_DEFAULT_GRID_HEIGHT,
    GENESIS_DEFAULT_GRID_WIDTH,
    MIN_MAP_LAND_FRACTION,
    continental_layout_terrain,
    is_solid_land_terrain,
    is_world_map_edge,
    map_land_fraction,
)
from realm.world.plot_parcels import plot_world_cells_tuple
from realm.world.terrain import Terrain


def _plot_land_fraction(plots: dict, width: int, height: int) -> float:
    land = 0
    total = width * height
    for y in range(height):
        for x in range(width):
            terrain: Terrain | None = None
            for plot in plots.values():
                if (x, y) in plot_world_cells_tuple(plot):
                    terrain = plot.terrain
                    break
            if terrain is not None and is_solid_land_terrain(terrain):
                land += 1
    return float(land) / float(total)


def test_continental_layout_meets_min_land_fraction() -> None:
    w, h = GENESIS_DEFAULT_GRID_WIDTH, GENESIS_DEFAULT_GRID_HEIGHT
    for seed in (0, 1, 42, 99, 592510244):
        frac = map_land_fraction(seed, w, h, continental_layout_terrain)
        assert frac >= MIN_MAP_LAND_FRACTION, f"seed {seed}: land fraction {frac:.3f}"


def test_genesis_bootstrap_meets_min_land_fraction() -> None:
    world = bootstrap_genesis(seed=42, settler_count=0)
    gw = int(world.scenario_state["grid_width"])
    gh = int(world.scenario_state["grid_height"])
    frac = _plot_land_fraction(world.plots, gw, gh)
    assert frac >= MIN_MAP_LAND_FRACTION


def test_map_edges_may_be_land() -> None:
    """Perimeter is no longer rewritten to deep ocean during plot generation."""
    w, h = 48, 36
    plots = generate_plots(seed=7, width=w, height=h, uniform_plots=True)
    edge_all_water = True
    for gx in range(w):
        for gy in range(h):
            if not is_world_map_edge(gx, gy, w, h):
                continue
            for plot in plots.values():
                if (gx, gy) not in plot_world_cells_tuple(plot):
                    continue
                if is_solid_land_terrain(plot.terrain):
                    edge_all_water = False
                break
    assert not edge_all_water, "expected at least one border cell to be solid land"

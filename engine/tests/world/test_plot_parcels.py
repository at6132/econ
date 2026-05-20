"""Multi-tile plot parcels (Option B)."""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.world import bootstrap_frontier, generate_plots
from realm.world.plot_parcels import build_world_cell_index, world_map_tile_count
from realm.world.plot_scale import plot_area_sq_metres, plot_grid_side, plot_world_tile_count
from realm.world.serialization import world_public_dict


def test_parcels_cover_every_map_cell() -> None:
    w = 12
    h = 8
    plots = generate_plots(seed=77, width=w, height=h)
    index = build_world_cell_index(plots)
    assert len(index) == w * h
    assert len(plots) < w * h


def test_multi_tile_parcel_grid_scales() -> None:
    plots = generate_plots(seed=88, width=10, height=10)
    multi = [p for p in plots.values() if plot_world_tile_count(p) > 1]
    assert multi
    p = multi[0]
    from realm.world.plot_scale import plot_world_span

    _, _, wt, ht = plot_world_span(p)
    gw, gh = plot_grid_side(p)
    assert gw == wt * 10
    assert gh == ht * 10
    assert plot_area_sq_metres(p) == plot_world_tile_count(p) * 10_000


def test_bootstrap_world_cell_index_and_public_dict() -> None:
    # Grid large enough for multi-tile parcels.
    world = bootstrap_frontier(seed=5, grid_width=12, grid_height=10)
    assert world_map_tile_count(world) == 120
    assert len(world.plots) < 120
    pub = world_public_dict(world)
    assert len(pub["world_cell_to_plot"]) == 120
    sample = next(p for p in pub["plots"] if len(p.get("world_cells", [])) > 1)
    assert sample["grid_cells_w"] == int(sample["world_tiles_w"]) * 10
    assert sample["area_sq_metres"] > 10_000


def test_uniform_plots_one_deed_per_cell() -> None:
    world = bootstrap_frontier(seed=9, grid_width=4, grid_height=3, uniform_plots=True)
    assert len(world.plots) == 12
    assert world_map_tile_count(world) == 12
    assert world.scenario_state["world_cell_to_plot"]["0,0"] == "p-0-0"


def test_world_cell_index_resolves_anchor() -> None:
    plots = generate_plots(seed=31, width=8, height=6)
    index = build_world_cell_index(plots)
    pid = PlotId(index["3,2"])
    assert pid in plots

"""Plot internal grid — cells_occupied and cells_free."""

from __future__ import annotations

from realm.production.blueprints import seed_world_blueprints
from realm.world import bootstrap_frontier
from realm.world.plot_scale import (
    cells_free,
    cells_occupied,
    plot_deed_grid_cells,
    plot_grid_side_for_id,
)
from realm.world.placed_buildings import PlacedBuilding, register_placed_building


def test_cells_occupied_correct() -> None:
    cells = cells_occupied(1, 1, 2, 3)
    assert len(cells) == 6
    assert (1, 1) in cells
    assert (2, 3) in cells


def test_cells_free_detects_overlap() -> None:
    world = bootstrap_frontier(seed=42, uniform_plots=True)
    seed_world_blueprints(world)
    plot_id = next(iter(world.plots))
    pid = str(plot_id)
    register_placed_building(
        world,
        PlacedBuilding(
            instance_id="pb_test01",
            blueprint_id="strip_mine",
            plot_id=pid,
            grid_x=0,
            grid_y=0,
            built_at_tick=0,
            built_by="player",
            status="active",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=0,
        ),
    )
    bp = world.blueprints["strip_mine"]
    assert cells_free(pid, world, 1, 1, 2, 2) is False


def test_cells_free_allows_adjacent() -> None:
    world = bootstrap_frontier(seed=42, uniform_plots=True)
    seed_world_blueprints(world)
    plot_id = next(iter(world.plots))
    pid = str(plot_id)
    register_placed_building(
        world,
        PlacedBuilding(
            instance_id="pb_test02",
            blueprint_id="power_shed",
            plot_id=pid,
            grid_x=0,
            grid_y=0,
            built_at_tick=0,
            built_by="player",
            status="active",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=0,
        ),
    )
    assert cells_free(pid, world, 2, 0, 2, 2) is True


def test_cells_free_rejects_out_of_bounds() -> None:
    world = bootstrap_frontier(seed=42, uniform_plots=True)
    seed_world_blueprints(world)
    plot_id = str(next(iter(world.plots)))
    gw, gh = plot_grid_side_for_id(world, plot_id)
    assert cells_free(plot_id, world, gw - 1, gh - 1, 2, 2) is False


def test_cells_free_rejects_bbox_corner_outside_polyomino_deed() -> None:
    from dataclasses import replace

    from realm.core.ids import PlotId

    world = bootstrap_frontier(seed=42, uniform_plots=True)
    seed_world_blueprints(world)
    plot_id = PlotId(str(next(iter(world.plots))))
    plot = world.plots[plot_id]
    world.plots[plot_id] = replace(
        plot,
        world_cells=((0, 0), (1, 0), (0, 1)),
        parcel_shape="l",
    )
    deed = plot_deed_grid_cells(world.plots[plot_id])
    gw, gh = plot_grid_side_for_id(world, str(plot_id))
    assert len(deed) < gw * gh
    void_gx, void_gy = gw - 5, gh - 5
    assert (void_gx, void_gy) not in deed
    assert cells_free(str(plot_id), world, void_gx, void_gy, 1, 1) is False

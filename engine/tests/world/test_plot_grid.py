"""Plot internal grid — cells_occupied and cells_free."""

from __future__ import annotations

from realm.production.blueprints import seed_world_blueprints
from realm.world import bootstrap_frontier
from realm.world.plot_scale import GRID_CELLS_PER_SIDE, cells_free, cells_occupied
from realm.world.placed_buildings import PlacedBuilding, register_placed_building


def test_cells_occupied_correct() -> None:
    cells = cells_occupied(1, 1, 2, 3)
    assert len(cells) == 6
    assert (1, 1) in cells
    assert (2, 3) in cells


def test_cells_free_detects_overlap() -> None:
    world = bootstrap_frontier(seed=42)
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
    world = bootstrap_frontier(seed=42)
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
    world = bootstrap_frontier(seed=42)
    seed_world_blueprints(world)
    plot_id = str(next(iter(world.plots)))
    assert cells_free(plot_id, world, 9, 9, 2, 2) is False

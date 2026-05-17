"""
Realm plot scale constants.

One plot = one real-world hectare (100m × 100m = 10,000 sq metres).
Each plot's internal grid is GRID_CELLS_PER_SIDE × GRID_CELLS_PER_SIDE.
One grid cell = 10m × 10m.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from realm.world.world import World

PLOT_SIDE_METRES: int = 100
GRID_CELLS_PER_SIDE: int = 10
CELL_SIDE_METRES: int = 10
PLOT_AREA_SQ_METRES: int = PLOT_SIDE_METRES**2


def cells_occupied(grid_x: int, grid_y: int, w: int, h: int) -> set[tuple[int, int]]:
    """Return all grid cells occupied by a rectangle at (grid_x, grid_y) with size w×h."""
    return {(grid_x + dx, grid_y + dy) for dx in range(w) for dy in range(h)}


def cells_free(
    plot_id: str,
    world: World,
    grid_x: int,
    grid_y: int,
    w: int,
    h: int,
    *,
    grid_side: int = GRID_CELLS_PER_SIDE,
) -> bool:
    """True if the rectangle fits on the plot grid and doesn't overlap any existing building."""
    if grid_x < 0 or grid_y < 0:
        return False
    if grid_x + w > grid_side or grid_y + h > grid_side:
        return False
    target_cells = cells_occupied(grid_x, grid_y, w, h)
    for iid in world.plot_placed_buildings.get(plot_id, []):
        pb = world.placed_buildings.get(iid)
        if pb is None:
            continue
        bp = world.blueprints.get(pb.blueprint_id)
        if bp is None:
            continue
        existing = cells_occupied(pb.grid_x, pb.grid_y, bp.footprint_w, bp.footprint_h)
        if target_cells & existing:
            return False
    return True

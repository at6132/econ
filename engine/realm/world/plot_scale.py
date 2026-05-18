"""
Realm plot scale constants.

One world map tile = one hectare (100m × 100m).
Internal build grid: 10×10 cells per world tile, 10m per cell.
A multi-tile parcel has (world_w × 10) × (world_h × 10) build cells.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from realm.core.ids import PlotId

if TYPE_CHECKING:
    from realm.world.world import Plot, World

CELLS_PER_WORLD_TILE: int = 10
PLOT_SIDE_METRES: int = 100
GRID_CELLS_PER_SIDE: int = 10  # per world tile
CELL_SIDE_METRES: int = 10
PLOT_AREA_SQ_METRES: int = PLOT_SIDE_METRES**2


def plot_world_cells_tuple(plot: Plot) -> tuple[tuple[int, int], ...]:
    if plot.world_cells:
        return plot.world_cells
    return ((plot.x, plot.y),)


def plot_world_tile_count(plot: Plot) -> int:
    return len(plot_world_cells_tuple(plot))


def plot_world_span(plot: Plot) -> tuple[int, int, int, int]:
    """``min_x, min_y, width_tiles, height_tiles`` bounding box."""
    cells = plot_world_cells_tuple(plot)
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    min_x = min(xs)
    min_y = min(ys)
    return min_x, min_y, max(xs) - min_x + 1, max(ys) - min_y + 1


def plot_grid_side(plot: Plot) -> tuple[int, int]:
    """Build-grid width and height in 10m cells."""
    _, _, wt, ht = plot_world_span(plot)
    return wt * CELLS_PER_WORLD_TILE, ht * CELLS_PER_WORLD_TILE


def plot_area_sq_metres(plot: Plot) -> int:
    return plot_world_tile_count(plot) * PLOT_AREA_SQ_METRES


def plot_deed_grid_cells(plot: Plot) -> set[tuple[int, int]]:
    """10m build cells that belong to this deed (polyomino-aware)."""
    cells = plot_world_cells_tuple(plot)
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    min_x = min(xs)
    min_y = min(ys)
    out: set[tuple[int, int]] = set()
    for wx, wy in cells:
        base_x = (wx - min_x) * CELLS_PER_WORLD_TILE
        base_y = (wy - min_y) * CELLS_PER_WORLD_TILE
        for dx in range(CELLS_PER_WORLD_TILE):
            for dy in range(CELLS_PER_WORLD_TILE):
                out.add((base_x + dx, base_y + dy))
    return out


def plot_grid_side_for_id(world: World, plot_id: PlotId | str) -> tuple[int, int]:
    plot = world.plots.get(PlotId(str(plot_id)))
    if plot is None:
        return GRID_CELLS_PER_SIDE, GRID_CELLS_PER_SIDE
    return plot_grid_side(plot)


def cells_occupied(grid_x: int, grid_y: int, w: int, h: int) -> set[tuple[int, int]]:
    return {(grid_x + dx, grid_y + dy) for dx in range(w) for dy in range(h)}


def cells_free(
    plot_id: str,
    world: World,
    grid_x: int,
    grid_y: int,
    w: int,
    h: int,
    *,
    grid_side_w: int | None = None,
    grid_side_h: int | None = None,
) -> bool:
    if grid_side_w is None or grid_side_h is None:
        grid_side_w, grid_side_h = plot_grid_side_for_id(world, plot_id)
    if grid_x < 0 or grid_y < 0:
        return False
    if grid_x + w > grid_side_w or grid_y + h > grid_side_h:
        return False
    target_cells = cells_occupied(grid_x, grid_y, w, h)
    plot = world.plots.get(PlotId(str(plot_id)))
    if plot is not None:
        deed = plot_deed_grid_cells(plot)
        if not target_cells.issubset(deed):
            return False
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

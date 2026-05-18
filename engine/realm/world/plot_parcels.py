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
from realm.world.plot_scale import plot_world_cells_tuple
from realm.world.world import Plot, Terrain, _subsurface_roll

# (width, height) in world map tiles; weights for parcel size roll.
_PARCEL_SHAPES: list[tuple[int, int, float]] = [
    (1, 1, 0.42),
    (2, 1, 0.14),
    (1, 2, 0.14),
    (2, 2, 0.18),
    (3, 2, 0.06),
    (2, 3, 0.04),
    (3, 3, 0.02),
]


def _pick_shape(rng: Any) -> tuple[int, int]:
    roll = rng.random()
    acc = 0.0
    for w, h, wt in _PARCEL_SHAPES:
        acc += wt
        if roll <= acc:
            return w, h
    return 1, 1


def _fits(
    assigned: list[list[str | None]],
    x: int,
    y: int,
    w: int,
    h: int,
    width: int,
    height: int,
) -> bool:
    if x + w > width or y + h > height:
        return False
    for dy in range(h):
        for dx in range(w):
            if assigned[y + dy][x + dx] is not None:
                return False
    return True


def _stamp(
    assigned: list[list[str | None]],
    x: int,
    y: int,
    w: int,
    h: int,
    pid: str,
) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for dy in range(h):
        for dx in range(w):
            assigned[y + dy][x + dx] = pid
            cells.append((x + dx, y + dy))
    return cells


def generate_plot_parcels(
    *,
    seed: int,
    width: int,
    height: int,
    correlate_subsurface: bool = False,
    terrain_fn: Callable[[int, int, int], Terrain] | None = None,
) -> dict[PlotId, Plot]:
    """
    Tile the world into non-overlapping rectangular parcels (1×1 … 3×3 tiles).
    Each parcel is one :class:`Plot`; anchor ``(x, y)`` is the min corner.
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
            _stamp(assigned, x, y, 1, 1, str(pid))
            sub_rng = make_rng(seed, f"gen:{pid}")
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
                world_cells=((x, y),),
            )

    for y in range(height):
        for x in range(width):
            if assigned[y][x] is not None:
                continue
            w, h = _pick_shape(rng)
            while w > 1 and not _fits(assigned, x, y, w, h, width, height):
                w -= 1
            while h > 1 and not _fits(assigned, x, y, w, h, width, height):
                h -= 1
            if not _fits(assigned, x, y, w, h, width, height):
                w, h = 1, 1
            pid = PlotId(f"p-{x}-{y}")
            cells = _stamp(assigned, x, y, w, h, str(pid))
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
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=anchor_terrain,
                owner=None,
                subsurface=subsurface,
                world_cells=tuple(cells),
            )
    clear_noise_cache()
    return plots


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
    return sum(plot_world_tile_count(p) for p in world.plots.values())


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
            )
    clear_noise_cache()
    return plots

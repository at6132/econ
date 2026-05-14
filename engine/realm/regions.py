"""Region abstraction — divide the world map into a 3 × 3 grid of regions.

A "region" is a coarse-grained geographic unit used by the shipping market
(Sprint 2 — Phase A). Each plot maps deterministically to one of nine
regions based on its (x, y) coordinates relative to the world grid bounds.
Region ids look like ``r-0-0`` (top-left), ``r-1-1`` (centre), ``r-2-2``
(bottom-right).

A "route" is an unordered pair of region ids. The canonical key for a route
is the two region ids joined by ``:`` in lexicographic order so that
shipping in either direction looks up the same record.
"""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.world import World


REGION_GRID_DIM: int = 3
"""3 × 3 grid → 9 regions total."""


def _world_bounds(world: World) -> tuple[int, int]:
    """Return ``(width, height)`` derived from the maximum plot coordinates.

    Genesis worlds are dense rectangular grids, so the maximum ``x`` + 1
    and the maximum ``y`` + 1 are reliable bounds. Falls back to ``(1, 1)``
    when the world has no plots (cheap defensive default).
    """
    if not world.plots:
        return (1, 1)
    max_x = 0
    max_y = 0
    for p in world.plots.values():
        if p.x > max_x:
            max_x = p.x
        if p.y > max_y:
            max_y = p.y
    return (max_x + 1, max_y + 1)


def region_for_coords(x: int, y: int, world_w: int, world_h: int) -> str:
    """Compute the region id for a plot at ``(x, y)`` inside an ``w × h`` world."""
    w = max(1, int(world_w))
    h = max(1, int(world_h))
    col = min(REGION_GRID_DIM - 1, max(0, int(int(x) * REGION_GRID_DIM // w)))
    row = min(REGION_GRID_DIM - 1, max(0, int(int(y) * REGION_GRID_DIM // h)))
    return f"r-{col}-{row}"


def region_for_plot(world: World, plot_id: PlotId) -> str | None:
    """Region id for the plot, or ``None`` if the plot is unknown."""
    plot = world.plots.get(plot_id)
    if plot is None:
        return None
    w, h = _world_bounds(world)
    return region_for_coords(plot.x, plot.y, w, h)


def route_key(region_a: str, region_b: str) -> str:
    """Canonical, direction-agnostic key for a region-to-region route."""
    a = str(region_a)
    b = str(region_b)
    return f"{a}:{b}" if a <= b else f"{b}:{a}"


def split_route_key(key: str) -> tuple[str, str]:
    """Inverse of ``route_key`` — returns the two region ids."""
    parts = str(key).split(":", 1)
    if len(parts) != 2:
        return (parts[0], "")
    return (parts[0], parts[1])


def all_region_ids() -> list[str]:
    """Every region id in the 3 × 3 grid (deterministic order, top-left → bottom-right)."""
    out: list[str] = []
    for col in range(REGION_GRID_DIM):
        for row in range(REGION_GRID_DIM):
            out.append(f"r-{col}-{row}")
    return out


def region_centre_coords(region_id: str, world_w: int, world_h: int) -> tuple[int, int]:
    """Approximate plot coordinates of the centre of ``region_id``.

    Used when an external system needs a representative plot for a region
    (e.g. siting NPC shippers). Returns integer coordinates clamped into the
    world. Falls back to ``(0, 0)`` for unparsable region ids.
    """
    parts = str(region_id).split("-")
    if len(parts) != 3 or parts[0] != "r":
        return (0, 0)
    try:
        col = int(parts[1])
        row = int(parts[2])
    except ValueError:
        return (0, 0)
    w = max(1, int(world_w))
    h = max(1, int(world_h))
    cx = (col * w // REGION_GRID_DIM) + (w // (2 * REGION_GRID_DIM))
    cy = (row * h // REGION_GRID_DIM) + (h // (2 * REGION_GRID_DIM))
    return (min(w - 1, cx), min(h - 1, cy))

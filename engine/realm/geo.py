"""Grid distance for movement cost (Primitive 4 / Law 3)."""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.world import World


def manhattan(world: World, plot_a: PlotId, plot_b: PlotId) -> int:
    pa = world.plots.get(plot_a)
    pb = world.plots.get(plot_b)
    if pa is None or pb is None:
        return 0
    return abs(pa.x - pb.x) + abs(pa.y - pb.y)


def plot_coords(world: World, plot_id: PlotId) -> tuple[int, int] | None:
    p = world.plots.get(plot_id)
    if p is None:
        return None
    return (p.x, p.y)

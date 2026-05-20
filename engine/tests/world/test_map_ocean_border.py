"""Legacy ``enforce_map_ocean_border`` helper (optional; not applied during worldgen)."""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.world.biome_noise import enforce_map_ocean_border, is_world_map_edge
from realm.world.plot_parcels import plot_world_cells_tuple
from realm.world.terrain import Terrain
from realm.world.world import Plot, SubsurfaceRoll


def test_enforce_map_ocean_border_splits_multicell_deed() -> None:
    w, h = 8, 8
    big = Plot(
        plot_id=PlotId("p-1-3"),
        x=1,
        y=3,
        terrain=Terrain.PLAINS,
        owner=None,
        subsurface=SubsurfaceRoll(0, 0, 0, 0),
        world_cells=((1, 3), (2, 3), (1, 4), (2, 4)),
    )
    plots = {big.plot_id: big}
    enforce_map_ocean_border(plots, w, h, seed=1)

    remnant = plots[PlotId("p-2-3")]
    assert remnant.terrain == Terrain.PLAINS
    assert set(plot_world_cells_tuple(remnant)) == {(2, 3), (2, 4)}

    for cx, cy in ((1, 3), (1, 4)):
        op = plots[PlotId(f"p-{cx}-{cy}")]
        assert op.terrain == Terrain.WATER_DEEP
        assert plot_world_cells_tuple(op) == ((cx, cy),)

    for gx in range(w):
        for gy in range(h):
            if not is_world_map_edge(gx, gy, w, h):
                continue
            pid = PlotId(f"p-{gx}-{gy}")
            assert pid in plots
            assert plots[pid].terrain == Terrain.WATER_DEEP

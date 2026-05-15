"""Mining externalities and soil remediation."""

from __future__ import annotations

from dataclasses import replace

from realm.actions import start_production_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.production.externalities import apply_mining_externality
from realm.production.production import tick_production
from realm.world import World, bootstrap_frontier
from realm.world.terrain import Terrain


def _minimal_world() -> World:
    return bootstrap_frontier(seed=900, grid_width=8, grid_height=4)


def test_mining_degrades_adjacent_agricultural_plots() -> None:
    w = _minimal_world()
    mine_pid = PlotId("p-2-2")
    farm_pid = PlotId("p-3-2")
    mp = w.plots[mine_pid]
    fp = w.plots[farm_pid]
    mp.terrain = Terrain.MOUNTAIN
    fp.terrain = Terrain.PLAINS
    mp.surveyed = True
    fp.surveyed = True
    start = float(fp.subsurface.phosphate_grade)
    for _ in range(20):
        apply_mining_externality(w, mine_pid)
    assert float(w.plots[farm_pid].subsurface.phosphate_grade) < start


def test_distant_plots_not_affected() -> None:
    w = _minimal_world()
    mine_pid = PlotId("p-1-1")
    far_pid = PlotId("p-7-3")
    w.plots[mine_pid].terrain = Terrain.MOUNTAIN
    w.plots[far_pid].terrain = Terrain.PLAINS
    w.plots[far_pid].surveyed = True
    start = float(w.plots[far_pid].subsurface.phosphate_grade)
    apply_mining_externality(w, mine_pid)
    assert float(w.plots[far_pid].subsurface.phosphate_grade) == start


def test_soil_degradation_blocks_farming() -> None:
    w = _minimal_world()
    pid = PlotId("p-2-2")
    pl = w.plots[pid]
    pl.terrain = Terrain.PLAINS
    pl.owner = PartyId("player")
    pl.surveyed = True
    pl.subsurface = replace(pl.subsurface, phosphate_grade=0.0)
    r = start_production_on_plot(w, PartyId("player"), pid, "grow_grain")
    assert r.get("ok") is False
    assert "soil" in str(r.get("reason", "")).lower()


def test_soil_remediation_restores_grade() -> None:
    w = _minimal_world()
    pid = PlotId("p-2-2")
    pl = w.plots[pid]
    pl.terrain = Terrain.PLAINS
    pl.owner = PartyId("player")
    pl.surveyed = True
    pl.subsurface = replace(pl.subsurface, phosphate_grade=0.25)
    p = PartyId("player")
    w.inventory.add(p, MaterialId("phosphate_meal"), 10)
    w.inventory.add(p, MaterialId("spade"), 1)
    r = start_production_on_plot(w, p, pid, "soil_remediation")
    assert r["ok"] is True
    run_id = r["run_id"]
    run = next(x for x in w.active_production if x.run_id == run_id)
    n = int(run.ticks_remaining)
    for _ in range(n):
        tick_production(w)
    assert float(w.plots[pid].subsurface.phosphate_grade) > 0.25


def test_degradation_feed_entry_at_threshold() -> None:
    w = _minimal_world()
    farm_pid = PlotId("p-3-2")
    fp = w.plots[farm_pid]
    fp.terrain = Terrain.PLAINS
    fp.surveyed = True
    fp.subsurface = replace(fp.subsurface, phosphate_grade=0.31)
    pre = len(w.event_log)
    apply_mining_externality(w, PlotId("p-2-2"))
    new = [e for e in w.event_log[pre:] if e.get("kind") == "world_feed"]
    assert new, "expected world_feed on soil threshold"

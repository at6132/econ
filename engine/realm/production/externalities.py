"""Mining externalities and agricultural soil quality (phosphate proxy)."""

from __future__ import annotations

from dataclasses import replace

from realm.events.event_log import log_event
from realm.core.ids import PlotId
from realm.world import World
from realm.world.terrain import Terrain


MINING_EXTERNALITY_RADIUS: int = 3
MINING_EXTERNALITY_DECAY: float = 0.0002

_AG_TERRAINS: frozenset[Terrain] = frozenset(
    {Terrain.PLAINS, Terrain.HILLS, Terrain.SWAMP, Terrain.TUNDRA, Terrain.DESERT}
)


def apply_mining_externality(world: World, mined_plot_id: PlotId) -> None:
    mined = world.plots.get(mined_plot_id)
    if mined is None:
        return
    mx, my = int(mined.x), int(mined.y)
    raw03 = world.scenario_state.setdefault("soil_feed_below_03", [])
    if not isinstance(raw03, list):
        raw03 = []
        world.scenario_state["soil_feed_below_03"] = raw03
    warned03: list[str] = raw03
    raw02 = world.scenario_state.setdefault("soil_feed_below_02", [])
    if not isinstance(raw02, list):
        raw02 = []
        world.scenario_state["soil_feed_below_02"] = raw02
    warned02: list[str] = raw02
    for plot in world.plots.values():
        dist = abs(int(plot.x) - mx) + abs(int(plot.y) - my)
        if dist == 0 or dist > MINING_EXTERNALITY_RADIUS:
            continue
        if plot.terrain not in _AG_TERRAINS:
            continue
        old = float(plot.subsurface.phosphate_grade)
        dec = MINING_EXTERNALITY_DECAY * (1.0 / float(dist))
        new = max(0.0, old - dec)
        plot.subsurface = replace(plot.subsurface, phosphate_grade=new)
        if new < 0.3 and old >= 0.3 and str(plot.plot_id) not in warned03:
            warned03.append(str(plot.plot_id))
            log_event(
                world,
                "world_feed",
                "Agricultural soil in the region is showing signs of industrial degradation.",
                plot_id=str(plot.plot_id),
                phosphate_grade=new,
            )
        if new < 0.2 and str(plot.plot_id) not in warned02:
            warned02.append(str(plot.plot_id))
            log_event(
                world,
                "world_feed",
                f"Farmland near {plot.plot_id} can no longer support crops. Mining activity in the area is to blame.",
                plot_id=str(plot.plot_id),
                phosphate_grade=new,
            )
        if new < 0.2 and old >= 0.2:
            log_event(
                world,
                "soil_degradation_warning",
                f"Soil quality at {plot.plot_id} has degraded from nearby mining.",
                plot_id=str(plot.plot_id),
                phosphate_grade=new,
            )


def soil_quality_modifier(world: World, plot_id: PlotId) -> float:
    plot = world.plots.get(plot_id)
    if plot is None:
        return 1.0
    grade = float(plot.subsurface.phosphate_grade)
    if grade >= 0.5:
        return 1.0
    if grade < 0.2:
        return 0.0
    return (grade - 0.2) / 0.3

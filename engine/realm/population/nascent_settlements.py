"""Phase 10F — two-residence clusters before formal town incorporation."""

from __future__ import annotations

from dataclasses import dataclass

from realm.core.ids import PlotId
from realm.events.event_log import log_event
from realm.population.towns import (
    TOWN_MIN_RESIDENCES,
    _active_residences,
    _cluster_residences,
)
from realm.world import World


@dataclass(frozen=True, slots=True)
class NascentSettlement:
    nascent_id: str
    island_id: int
    anchor_plot_id: PlotId
    member_plot_ids: tuple[PlotId, ...]
    resident_count: int
    consecutive_game_days: int
    last_checked_tick: int


def _cluster_id(member_ids: tuple[str, ...]) -> str:
    return "ns-" + ":".join(sorted(member_ids))


def refresh_nascent_settlements(world: World) -> None:
    """Rebuild nascent rows from residence clusters of size exactly two."""
    residences = _active_residences(world)
    clusters = _cluster_residences(residences)
    plot_islands = world.scenario_state.get("plot_islands") or {}
    prev = dict(world.nascent_settlements)
    next_map: dict[str, NascentSettlement] = {}
    for cluster in clusters:
        if len(cluster) != TOWN_MIN_RESIDENCES - 1:
            continue
        member_strs = tuple(sorted(str(r[0]) for r in cluster))
        nid = _cluster_id(member_strs)
        anchor = PlotId(member_strs[0])
        plot = world.plots.get(anchor)
        isl = int(plot_islands.get(str(anchor), 0)) if plot is not None else 0
        old = prev.get(nid)
        if old is not None and tuple(str(p) for p in old.member_plot_ids) == member_strs:
            streak = int(old.consecutive_game_days)
        else:
            streak = 0
        next_map[nid] = NascentSettlement(
            nascent_id=nid,
            island_id=isl,
            anchor_plot_id=anchor,
            member_plot_ids=tuple(PlotId(s) for s in member_strs),
            resident_count=len(member_strs),
            consecutive_game_days=streak,
            last_checked_tick=int(world.tick),
        )
    world.nascent_settlements = next_map


def tick_nascent_settlements(world: World) -> None:
    """Daily: refresh geometry then age streaks; feed when crossing day 3."""
    if int(world.tick) <= 0 or int(world.tick) % 1440 != 0:
        return
    prev_streaks = {nid: int(ns.consecutive_game_days) for nid, ns in world.nascent_settlements.items()}
    refresh_nascent_settlements(world)
    bumped: dict[str, NascentSettlement] = {}
    for nid, ns in world.nascent_settlements.items():
        new_days = int(ns.consecutive_game_days) + 1
        bumped[nid] = NascentSettlement(
            nascent_id=ns.nascent_id,
            island_id=ns.island_id,
            anchor_plot_id=ns.anchor_plot_id,
            member_plot_ids=ns.member_plot_ids,
            resident_count=ns.resident_count,
            consecutive_game_days=new_days,
            last_checked_tick=int(world.tick),
        )
    world.nascent_settlements = bumped
    for nid, ns in bumped.items():
        old = int(prev_streaks.get(nid, -1))
        if ns.consecutive_game_days == 3 and old == 2:
            log_event(
                world,
                "world_feed",
                f"A nascent settlement stabilised near {ns.anchor_plot_id} "
                f"({ns.resident_count} residences, {ns.consecutive_game_days} days).",
                nascent_id=nid,
            )


def on_residence_built_nascent(world: World, plot_id: PlotId) -> None:
    _ = plot_id
    refresh_nascent_settlements(world)

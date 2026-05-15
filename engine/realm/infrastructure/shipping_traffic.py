"""Rolling voyage counts per route (Phase 10B).

``world.voyage_history`` is cumulative (all-time). NPC route discovery uses
``scenario_state["route_voyage_by_day"]``: ``game_day_index -> {route_key: count}``
so we can sum the last 7 game-days deterministically.
"""

from __future__ import annotations

from typing import Final

from realm.world import World

TICKS_PER_GAME_DAY: Final[int] = 1440
_DEFAULT_WINDOW_DAYS: Final[int] = 7
_PRUNE_KEEP_DAYS: Final[int] = 21


def record_route_voyage_completed(world: World, route_key: str) -> None:
    """Call from ``deliver_transit`` when a shipment completes on ``route_key``."""
    d = int(world.tick) // TICKS_PER_GAME_DAY
    outer = world.scenario_state.setdefault("route_voyage_by_day", {})
    if not isinstance(outer, dict):
        outer = {}
        world.scenario_state["route_voyage_by_day"] = outer
    day_bucket = outer.setdefault(str(d), {})
    if not isinstance(day_bucket, dict):
        day_bucket = {}
        outer[str(d)] = day_bucket
    rk = str(route_key)
    day_bucket[rk] = int(day_bucket.get(rk, 0)) + 1


def route_voyage_count_last_days(
    world: World, route_key: str, *, days: int = _DEFAULT_WINDOW_DAYS
) -> int:
    """Sum completed voyages on ``route_key`` over the last ``days`` game-days."""
    d_cur = int(world.tick) // TICKS_PER_GAME_DAY
    outer = world.scenario_state.get("route_voyage_by_day") or {}
    if not isinstance(outer, dict):
        return 0
    total = 0
    for i in range(int(days)):
        dm = outer.get(str(d_cur - i))
        if isinstance(dm, dict):
            total += int(dm.get(str(route_key), 0))
    return total


def prune_route_voyage_by_day(world: World, *, keep_days: int = _PRUNE_KEEP_DAYS) -> None:
    """Drop day buckets older than ``keep_days`` before the current game-day."""
    outer = world.scenario_state.get("route_voyage_by_day")
    if not isinstance(outer, dict):
        return
    d_cur = int(world.tick) // TICKS_PER_GAME_DAY
    cutoff = d_cur - int(keep_days)
    for dk in list(outer.keys()):
        try:
            if int(dk) < cutoff:
                outer.pop(dk, None)
        except (TypeError, ValueError):
            outer.pop(dk, None)

"""Genesis NPC economy must keep producing past the road-grace / depletion window."""

from __future__ import annotations

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def _drain_production(world, seen: set[int]) -> int:
    n = 0
    for e in world.event_log:
        eid = id(e)
        if eid in seen:
            continue
        seen.add(eid)
        if str(e.get("kind") or "") == "production_done":
            n += 1
    return n


def test_production_and_wages_continue_past_day_45() -> None:
    w = bootstrap_genesis(seed=42, grid_width=48, grid_height=36, settler_count=8)
    seen: set[int] = set()
    checkpoints = [(30, 40), (45, 8), (60, 8)]
    prev_prod = 0
    for days, min_delta in checkpoints:
        target = days * TICKS_PER_GAME_DAY
        while w.tick < target:
            advance_tick(w)
        prod = prev_prod + _drain_production(w, seen)
        assert prod >= min_delta if prev_prod == 0 else prod >= prev_prod + min_delta, (
            f"production stalled by day {days}: {prev_prod} -> {prod}"
        )
        prev_prod = prod
    assert len(w.laborers) >= 60, f"labor collapse: {len(w.laborers)}"

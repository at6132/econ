"""Genesis NPC economy must keep producing past the road-grace / depletion window."""

from __future__ import annotations

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def _total_settler_production(world) -> int:
    ops = world.scenario_state.get("settler_ops_completed") or {}
    return sum(int(v) for v in ops.values())


def _settler_parties_with_plots(world) -> int:
    return sum(
        1
        for p in world.parties
        if str(p).startswith("settler_")
        and any(pl.owner == p for pl in world.plots.values())
    )


def test_npc_tenders_posted_in_first_month() -> None:
    w = bootstrap_genesis(seed=42, grid_width=48, grid_height=36, settler_count=8)
    target = 35 * TICKS_PER_GAME_DAY
    while w.tick < target:
        advance_tick(w)
    from realm.contracts.tenders import list_all_tenders

    all_t = list_all_tenders(w)
    assert len(all_t) >= 1, "anchor buyers should post supply tenders"


def test_production_and_wages_continue_past_day_45() -> None:
    w = bootstrap_genesis(seed=42, grid_width=48, grid_height=36, settler_count=8)
    checkpoints = [(30, 40), (45, 8)]
    prev_prod = 0
    for days, min_delta in checkpoints:
        target = days * TICKS_PER_GAME_DAY
        while w.tick < target:
            advance_tick(w)
        prod = _total_settler_production(w)
        assert prod >= min_delta if prev_prod == 0 else prod >= prev_prod + min_delta, (
            f"production stalled by day {days}: {prev_prod} -> {prod}"
        )
        prev_prod = prod
    while w.tick < 90 * TICKS_PER_GAME_DAY:
        advance_tick(w)
    prod_90 = _total_settler_production(w)
    assert prod_90 >= prev_prod + 15, (
        f"production did not grow day 45->90: {prev_prod} -> {prod_90}"
    )
    assert prod_90 >= 450, f"production too low by day 90: {prod_90}"
    assert _settler_parties_with_plots(w) >= 5, (
        f"too many settlers lost their plots: {_settler_parties_with_plots(w)}"
    )
    assert len(w.laborers) >= 60, f"labor collapse: {len(w.laborers)}"
    while w.tick < 120 * TICKS_PER_GAME_DAY:
        advance_tick(w)
    prod_120 = _total_settler_production(w)
    assert prod_120 >= prod_90, (
        f"production declined day 90->120: {prod_90} -> {prod_120}"
    )
    from realm.contracts.tenders import list_all_tenders

    awarded = sum(
        1 for t in list_all_tenders(w) if str(t.get("status")) == "awarded"
    )
    assert awarded >= 1, f"expected tender awards by day 120: {awarded}"
    assert len(w.laborers) >= 55, f"labor pool collapsed by day 120: {len(w.laborers)}"

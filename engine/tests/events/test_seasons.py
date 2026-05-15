"""Phase 8 — Sub-phase 8A: seasonal calendar tests.

Covers the contract laid out in the Sub-phase 8A spec:
  * ``grow_grain`` blocked in winter on non-tropical islands
  * Autumn harvest window surges output above the base recipe yield
  * Winter fuel-need decay > summer decay
  * Each season transition emits a world-feed entry
  * Tropical islands (id 1) still grow grain in winter at ×0.5
"""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.events.seasons import (
    AUTUMN_START,
    HARVEST_DECLINE_START,
    SPRING_START,
    SUMMER_START,
    Season,
    TICKS_PER_GAME_YEAR,
    WINTER_START,
    current_game_day_of_year,
    current_season,
    fuel_decay_per_day_for_season,
    recipe_blocked_by_season,
    tick_seasons,
    yield_modifier,
)
from realm.production import effective_outputs_for_completion
from realm.production.recipes import RECIPES
from realm.world import ActiveProduction, bootstrap_frontier, bootstrap_genesis
from realm.world.terrain import Terrain

_TICKS_PER_GAME_DAY = 1440


def _tick_for_day(day: int) -> int:
    """Tick at the *first minute* of ``day`` (1-indexed day of year)."""
    return (day - 1) * _TICKS_PER_GAME_DAY


def _player_plot_on_terrain(world, terrain: Terrain) -> PlotId:
    """Find an unclaimed plot of ``terrain`` and claim it for ``player``."""
    party = PartyId("player")
    # Make sure the player has enough cash for any claim cost.
    cash = party_cash_account(party)
    world.ledger.ensure_account(cash)
    if world.ledger.balance(cash) < 1_000_000:
        world.ledger.transfer(
            debit=system_reserve_account(),
            credit=cash,
            amount_cents=1_000_000,
        )
    for plot_id, plot in world.plots.items():
        if plot.owner is None and plot.terrain == terrain:
            r = claim_plot(world, party, plot_id)
            assert r.get("ok"), f"failed to claim plot: {r}"
            world.plots[plot_id].surveyed = True
            return plot_id
    raise AssertionError(f"no {terrain} plot available to claim")


# ─────────────────────────────────────────────────────────────────────
# A5.1 — grow_grain blocked in winter on non-tropical land
# ─────────────────────────────────────────────────────────────────────


def test_grow_grain_blocked_in_winter() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    w.tick = _tick_for_day(310)  # mid-winter
    assert current_season(w) is Season.WINTER, "fixture should now be in winter"

    # Pick any plains plot on a non-tropical island (island 0/2/3).
    plot_islands = w.scenario_state.get("plot_islands", {})
    pid: PlotId | None = None
    for plot_id_s, isl in plot_islands.items():
        if int(isl) == 1:
            continue
        plot = w.plots.get(PlotId(plot_id_s))
        if plot is None or plot.terrain != Terrain.PLAINS or plot.owner is not None:
            continue
        pid = PlotId(plot_id_s)
        break
    if pid is None:
        # Fall back to ANY non-tropical plot — terrain gating belongs to a
        # different layer; the seasonal block fires before terrain checks.
        for plot_id_s, isl in plot_islands.items():
            if int(isl) == 1:
                continue
            plot = w.plots.get(PlotId(plot_id_s))
            if plot is None or plot.owner is not None:
                continue
            pid = PlotId(plot_id_s)
            break
    assert pid is not None, "expected at least one non-tropical unclaimed plot"
    plot = w.plots[pid]

    blocked, reason = recipe_blocked_by_season(w, "grow_grain", plot)
    assert blocked is True
    assert "winter" in reason.lower()


# ─────────────────────────────────────────────────────────────────────
# A5.2 — Autumn harvest window surges output above base
# ─────────────────────────────────────────────────────────────────────


def test_harvest_surge_multiplier() -> None:
    """Day 250 (mid harvest window) → ``grow_grain`` produces 1.5× base."""
    w = bootstrap_frontier(seed=42)
    w.tick = _tick_for_day(250)
    assert current_season(w) is Season.AUTUMN
    assert AUTUMN_START <= current_game_day_of_year(w) < HARVEST_DECLINE_START

    # Direct modifier check.
    mod = yield_modifier(w, "grow_grain", None)
    assert mod == 1.5

    # Verify the modifier composes inside effective_outputs_for_completion.
    recipe = RECIPES["grow_grain"]
    sample_pid = next(iter(w.plots))
    from dataclasses import replace

    sp = w.plots[sample_pid]
    sp.subsurface = replace(sp.subsurface, phosphate_grade=0.9)
    run = ActiveProduction(
        run_id="run_harvest_test",
        party=PartyId("player"),
        plot_id=sample_pid,
        recipe_id="grow_grain",
        ticks_remaining=0,
    )
    out_autumn = effective_outputs_for_completion(w, run, recipe)
    base_qty = int(recipe.outputs[MaterialId("grain")])
    autumn_qty = int(out_autumn[MaterialId("grain")])
    # In autumn harvest window, output should be strictly above base.
    assert autumn_qty > base_qty, (
        f"expected harvest output > base ({base_qty}), got {autumn_qty}"
    )
    # And specifically 1.5x (round-trip through the modifier).
    assert autumn_qty == round(base_qty * 1.5)


# ─────────────────────────────────────────────────────────────────────
# A5.3 — winter fuel decay > summer fuel decay
# ─────────────────────────────────────────────────────────────────────


def test_winter_fuel_decay_higher() -> None:
    summer = fuel_decay_per_day_for_season(Season.SUMMER)
    winter = fuel_decay_per_day_for_season(Season.WINTER)
    autumn = fuel_decay_per_day_for_season(Season.AUTUMN)
    spring = fuel_decay_per_day_for_season(Season.SPRING)
    assert winter > autumn > summer == spring
    # Per spec: winter is nearly 2x summer.
    assert winter >= 2.0 * summer


# ─────────────────────────────────────────────────────────────────────
# A5.4 — every season transition fires a world_feed entry
# ─────────────────────────────────────────────────────────────────────


def test_seasonal_feed_entries_fire() -> None:
    """Tick across all four canonical boundaries; assert ≥ 4 transition entries."""
    w = bootstrap_frontier(seed=42)
    boundaries = [SPRING_START, SUMMER_START, AUTUMN_START, WINTER_START]
    for day in boundaries:
        w.tick = _tick_for_day(day)
        tick_seasons(w)

    transitions = [
        row for row in w.world_feed_log
        if row.get("event_class") == "season_transition"
    ]
    seasons_seen = {row.get("season") for row in transitions}
    assert {"spring", "summer", "autumn", "winter"}.issubset(seasons_seen), (
        f"expected all four seasons in feed, saw {seasons_seen}"
    )
    # Each boundary should fire exactly once even if tick_seasons is called twice.
    tick_seasons(w)
    transitions_after_replay = [
        row for row in w.world_feed_log
        if row.get("event_class") == "season_transition"
    ]
    assert len(transitions_after_replay) == len(transitions), (
        "second call to tick_seasons should be idempotent within the same day"
    )


def test_seasonal_feed_entries_replay_next_year() -> None:
    """Year-2 boundaries must fire fresh entries (not de-duped against year 1)."""
    w = bootstrap_frontier(seed=42)
    w.tick = _tick_for_day(SPRING_START)
    tick_seasons(w)
    w.tick = _tick_for_day(SPRING_START) + TICKS_PER_GAME_YEAR
    tick_seasons(w)
    transitions = [
        row for row in w.world_feed_log
        if row.get("event_class") == "season_transition" and row.get("season") == "spring"
    ]
    years = {row.get("year") for row in transitions}
    assert {0, 1}.issubset(years), f"expected year 0 AND year 1 spring entries, saw {years}"


# ─────────────────────────────────────────────────────────────────────
# A5.5 — tropical island (id=1) grows grain in winter at ×0.5
# ─────────────────────────────────────────────────────────────────────


def test_tropical_island_grows_in_winter() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    w.tick = _tick_for_day(310)  # mid-winter
    assert current_season(w) is Season.WINTER

    plot_islands = w.scenario_state.get("plot_islands", {})
    tropical_pid: PlotId | None = None
    for plot_id_s, isl in plot_islands.items():
        if int(isl) != 1:
            continue
        plot = w.plots.get(PlotId(plot_id_s))
        if plot is None:
            continue
        tropical_pid = PlotId(plot_id_s)
        break
    assert tropical_pid is not None, "genesis seed=42 must have island 1 (tropical)"
    tropical_plot = w.plots[tropical_pid]

    mod = yield_modifier(w, "grow_grain", tropical_plot)
    assert mod == 0.5, f"tropical winter mod should be 0.5, got {mod}"

    # And the recipe is NOT blocked at start-time on tropical land.
    blocked, _ = recipe_blocked_by_season(w, "grow_grain", tropical_plot)
    assert blocked is False, "tropical island should still allow grow_grain in winter"

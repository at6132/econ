"""Week-1 employment ramp — settlers hire laborers as the job market runs."""

from __future__ import annotations

import pytest

from realm.genesis.settler_upgrades import tick_settler_margin_review
from realm.population.employment import (
    active_employment_count,
    tick_job_market,
    tick_laborer_wages,
    tick_settler_job_postings,
)
from realm.world import bootstrap_genesis

TICKS_PER_GAME_DAY = 1440
TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY


@pytest.fixture(autouse=True)
def _disable_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REALM_LLM_DISABLE", "1")


def _advance_genesis_employment_days(world: object, days: int) -> None:
    """Step the job-market pipeline on each game-day boundary.

    Full ``advance_tick`` × 7×1440 is correct but too slow for CI on genesis
    worlds (settler agent pipeline dominates). This exercises the same
    employment hooks ``advance_tick`` invokes on day boundaries.
    """
    for day in range(1, days + 1):
        world.tick = day * TICKS_PER_GAME_DAY
        tick_settler_job_postings(world)
        tick_job_market(world)
        tick_laborer_wages(world)
        if int(world.tick) % TICKS_PER_GAME_WEEK == 0:
            tick_settler_margin_review(world)


def test_employment_reaches_10pct_within_7_days() -> None:
    """With the job market wired, employment should reach at least 10% within 7 game-days."""
    w = bootstrap_genesis(
        seed=7, settler_count=20, grid_width=64, grid_height=48, map_layout="continental"
    )
    start = w.ledger.total_cents()
    total_laborers = len(w.laborers)
    assert total_laborers > 0

    _advance_genesis_employment_days(w, 7)

    employed = active_employment_count(w)
    employment_rate = employed / total_laborers

    assert employment_rate >= 0.10, (
        f"Employment after 7 days: {employed}/{total_laborers} = "
        f"{employment_rate:.1%} — expected ≥10%"
    )
    assert w.ledger.total_cents() == start, "Wage payments violated conservation"


def test_job_postings_appear_within_weekly_review() -> None:
    """After one game-week, settlers with active buildings should have posted openings."""
    w = bootstrap_genesis(
        seed=1, settler_count=10, grid_width=64, grid_height=48, map_layout="continental"
    )

    _advance_genesis_employment_days(w, 7)

    open_count = sum(1 for o in w.job_openings if o.filled_by is None)
    filled_count = sum(1 for o in w.job_openings if o.filled_by is not None)

    assert open_count + filled_count >= 5, (
        f"Expected ≥5 job openings after 1 week, got {open_count} open + {filled_count} filled"
    )

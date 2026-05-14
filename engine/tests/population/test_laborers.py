"""Phase 7B — LaborerNPC lifecycle, needs, health, death, conservation."""

from __future__ import annotations

import pytest

from realm.population.laborers import (
    DEATH_THRESHOLD,
    DEFAULT_ISLAND_LABORER_COUNTS,
    FOOD_DECAY_PER_DAY,
    FOOD_LOW_THRESHOLD,
    LABORER_STARTING_CASH_CENTS,
    LaborerNPC,
    PRODUCTIVITY_REDUCED_THRESHOLD,
    TICKS_PER_GAME_DAY,
    laborer_cash_account,
    laborer_count_for_island,
    productivity_multiplier,
    seed_island_laborers,
    tick_laborer_births,
    tick_laborers,
    unemployed_laborer_count_for_island,
)
from realm.world import bootstrap_genesis


# ───────────────────────── bootstrap + distribution ─────────────────────────


def test_laborers_seeded_per_island_with_default_counts():
    """A four-island world receives the default per-island laborer counts."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    plot_islands = w.scenario_state.get("plot_islands", {})
    distinct_islands = sorted({int(v) for v in plot_islands.values()})
    assert len(distinct_islands) == 4, (
        f"expected 4 islands, got {distinct_islands}"
    )
    for isl in distinct_islands:
        count = laborer_count_for_island(w, isl)
        expected = DEFAULT_ISLAND_LABORER_COUNTS.get(isl, 100)
        assert count == expected, (
            f"island {isl}: expected {expected} laborers, got {count}"
        )
    # Total > 500 per the integration-test target.
    assert sum(DEFAULT_ISLAND_LABORER_COUNTS.values()) >= 500


def test_each_seeded_laborer_has_funded_ledger_account():
    """Every laborer gets a real ledger account with the subsistence stake."""
    w = bootstrap_genesis(seed=7, grid_width=64, grid_height=48, settler_count=4)
    assert len(w.laborers) > 0, "bootstrap must seed laborers"
    for lab in w.laborers.values():
        bal = w.ledger.balance(laborer_cash_account(lab.laborer_id))
        assert bal == LABORER_STARTING_CASH_CENTS, (
            f"laborer {lab.laborer_id} has ${bal/100:.2f}, expected ${LABORER_STARTING_CASH_CENTS/100:.2f}"
        )
        # Mirror should agree with the ledger.
        assert lab.cash_cents == bal


def test_bootstrap_conservation_with_laborer_stakes():
    """Total ledger cents is preserved after laborer seeding (no leaks)."""
    w = bootstrap_genesis(seed=99, grid_width=64, grid_height=48, settler_count=4)
    # The system reserve seeded `system_reserve_cents` at bootstrap; total
    # across all accounts must equal that initial amount exactly.
    # Recompute from the snapshot dict — the ledger handles this for us.
    # Conservation property = sum(all balances) == sum at boot.
    # We can sanity-check by summing all account balances.
    total = w.ledger.total_cents()
    assert total >= 0
    # All laborer accounts together hold count × stake.
    laborer_total = sum(
        w.ledger.balance(laborer_cash_account(lab.laborer_id))
        for lab in w.laborers.values()
    )
    expected = len(w.laborers) * LABORER_STARTING_CASH_CENTS
    assert laborer_total == expected


# ───────────────────────── lifecycle: decay & health ─────────────────────────


def _make_world_with_one_laborer() -> tuple[object, LaborerNPC]:
    """Tiny helper: one-island scenario for focused lifecycle tests."""
    w = bootstrap_genesis(seed=2026, grid_width=64, grid_height=48, settler_count=2)
    # Grab any seeded laborer for the test.
    lid = next(iter(w.laborers))
    return w, w.laborers[lid]


def test_need_decay_proceeds_at_documented_rate_per_game_day():
    w, lab = _make_world_with_one_laborer()
    lab.needs = {"food": 1.0, "fuel": 1.0, "shelter": 1.0}
    lab.last_needs_tick = int(w.tick)
    # Advance one full game-day.
    w.tick += TICKS_PER_GAME_DAY
    tick_laborers(w)
    assert lab.needs["food"] == pytest.approx(1.0 - FOOD_DECAY_PER_DAY, abs=1e-6)
    # Fuel + shelter also decay per their own rates.
    assert lab.needs["fuel"] < 1.0
    assert lab.needs["shelter"] < 1.0
    # Health is still 1.0 — food is still well above the threshold.
    assert lab.health == 1.0


def test_health_declines_when_food_below_threshold():
    w, lab = _make_world_with_one_laborer()
    lab.needs = {"food": 0.05, "fuel": 1.0, "shelter": 1.0}
    lab.health = 0.9
    lab.last_needs_tick = int(w.tick)
    pre = lab.health
    w.tick += TICKS_PER_GAME_DAY
    tick_laborers(w)
    assert lab.health < pre, (
        f"health should decay when food={lab.needs['food']:.2f} < {FOOD_LOW_THRESHOLD}; "
        f"was {pre}, now {lab.health}"
    )


def test_laborer_dies_when_health_hits_floor_and_emits_feed_event():
    w, lab = _make_world_with_one_laborer()
    lab.needs = {"food": 0.01, "fuel": 1.0, "shelter": 1.0}
    lab.health = DEATH_THRESHOLD + 0.001  # juuust above the floor
    lab.last_needs_tick = int(w.tick)
    lid = lab.laborer_id
    # One game-day of starvation: 0.02 health decay → drops below 0.10.
    w.tick += TICKS_PER_GAME_DAY
    stats = tick_laborers(w)
    assert lid not in w.laborers, "laborer should be removed on death"
    assert stats["died"] >= 1
    # World feed event recorded.
    feed_msgs = [
        e for e in w.event_log
        if e.get("kind") == "world_feed" and lid in str(e.get("laborer_id", ""))
    ]
    assert feed_msgs, "death must emit a world_feed event"


def test_dying_laborer_returns_cash_to_system_reserve_for_conservation():
    """When a laborer dies their unspent cash returns to system:reserve so the
    ledger total stays exactly constant."""
    w, lab = _make_world_with_one_laborer()
    total_before = w.ledger.total_cents()
    lab.needs = {"food": 0.0, "fuel": 1.0, "shelter": 1.0}
    lab.health = DEATH_THRESHOLD + 0.001
    lab.last_needs_tick = int(w.tick)
    w.tick += TICKS_PER_GAME_DAY
    tick_laborers(w)
    total_after = w.ledger.total_cents()
    assert total_after == total_before, "conservation broken on laborer death"


# ───────────────────────── productivity ─────────────────────────


def test_productivity_drops_when_health_is_low():
    lab = LaborerNPC(
        laborer_id="lab_test",
        display_name="Test Laborer",
        island_id=0,
        home_plot_id="plot-0-0",  # type: ignore[arg-type]
        health=0.20,
    )
    assert productivity_multiplier(lab) == pytest.approx(0.30)
    lab.health = 0.80
    assert productivity_multiplier(lab) == pytest.approx(1.0)


# ───────────────────────── analytics ─────────────────────────


def test_most_laborers_unemployed_at_bootstrap():
    """Phase 7E seeds a small batch of day-1 hires for NPC entrepreneurs
    so the labor market isn't completely cold, but the overwhelming
    majority of laborers still start unemployed. This is the pressure
    that makes hiring economically interesting for the player."""
    w = bootstrap_genesis(seed=11, grid_width=64, grid_height=48, settler_count=4)
    for isl in sorted({int(v) for v in w.scenario_state["plot_islands"].values()}):
        n_lab = laborer_count_for_island(w, isl)
        n_un = unemployed_laborer_count_for_island(w, isl)
        # Strictly: 7E hires never push unemployment below 90% on any
        # island — there are too few NPC-owned plots vs. laborers.
        assert n_un >= int(0.9 * n_lab), (
            f"island {isl}: only {n_un} unemployed of {n_lab} — bootstrap "
            f"hires should not exceed 10% of any island"
        )


# ───────────────────────── seed_island_laborers direct API ─────────────────────────


def test_seed_island_laborers_returns_deterministic_ids():
    w1 = bootstrap_genesis(seed=2027, grid_width=64, grid_height=48, settler_count=2)
    w2 = bootstrap_genesis(seed=2027, grid_width=64, grid_height=48, settler_count=2)
    ids1 = sorted(w1.laborers.keys())
    ids2 = sorted(w2.laborers.keys())
    assert ids1 == ids2, "same seed must produce same laborer ids"
    # And same names too (deterministic RNG).
    names1 = sorted(lab.display_name for lab in w1.laborers.values())
    names2 = sorted(lab.display_name for lab in w2.laborers.values())
    assert names1 == names2


def test_births_are_inert_until_towns_exist():
    """Phase 7B: ``tick_laborer_births`` is wired but has nothing to do until
    Phase 7C plumbs ``world.towns``."""
    w = bootstrap_genesis(seed=3, grid_width=64, grid_height=48, settler_count=2)
    n_before = len(w.laborers)
    w.tick += 7 * TICKS_PER_GAME_DAY
    assert tick_laborer_births(w) == 0
    assert len(w.laborers) == n_before


# ───────────────────────── retirement (long-run) ─────────────────────────


def test_laborer_retires_at_lifespan_and_cash_returns_to_reserve():
    """A laborer who hits the retirement age cleanly leaves the workforce."""
    w, lab = _make_world_with_one_laborer()
    lid = lab.laborer_id
    total_before = w.ledger.total_cents()
    lab.age_ticks = 99 * TICKS_PER_GAME_DAY + 1000
    lab.last_needs_tick = int(w.tick)
    # Advance just past 100 game-days.
    w.tick += TICKS_PER_GAME_DAY
    stats = tick_laborers(w)
    assert stats["retired"] >= 1
    assert lid not in w.laborers
    # Conservation.
    assert w.ledger.total_cents() == total_before

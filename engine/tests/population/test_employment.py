"""Phase 7E — real employment market, wages as ledger transfers."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.population.employment import (
    DEFAULT_WAGE_PER_GAME_DAY_CENTS,
    JOB_SEARCH_RADIUS_TILES,
    active_employment_count,
    cancel_job_opening,
    job_openings_for_employer,
    post_job_opening,
    tick_job_market,
    tick_laborer_wages,
)
from realm.core.ids import PartyId, PlotId
from realm.population.laborers import (
    LABORER_STARTING_CASH_CENTS,
    TICKS_PER_GAME_DAY,
    laborer_cash_account,
)
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world.terrain import Terrain
from realm.world import bootstrap_genesis


# ───────────────────────── bootstrap day-1 employment ─────────────────────────


def test_bootstrap_seeds_day1_openings_and_employment():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    seed_report = w.scenario_state.get("starting_job_market", {})
    assert int(seed_report.get("openings_posted", 0)) > 0
    assert int(seed_report.get("hired_immediately", 0)) > 0
    employed = active_employment_count(w)
    assert employed == int(seed_report["hired_immediately"])


def test_bootstrap_ledger_conserved_after_employment_seeding():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    # Seed reserve is exactly $1_000_000.00 = 100_000_000_000 cents.
    assert w.ledger.total_cents() == 100_000_000_000


# ───────────────────────── post / cancel ─────────────────────────


def test_post_job_opening_requires_plot_ownership():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player = PartyId("player")
    other_pid: PlotId | None = None
    for p in w.plots.values():
        if p.owner is not None and p.owner != player:
            other_pid = p.plot_id
            break
    assert other_pid is not None
    res = post_job_opening(w, player, other_pid)
    assert not res["ok"]
    assert "not your plot" in res["reason"]


def test_post_job_opening_and_cancel_round_trip():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player = PartyId("player")
    # Fund + claim an empty plot.
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=1_000_000,
    )
    pid = next(
        p.plot_id
        for p in w.plots.values()
        if p.owner is None and p.terrain not in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW)
    )
    claim_plot(w, player, pid)
    res = post_job_opening(w, player, pid, skill_min=2, wage_per_day_cents=1200)
    assert res["ok"], res
    opening_id = res["opening_id"]
    openings = job_openings_for_employer(w, player)
    assert len(openings) == 1
    assert openings[0].opening_id == opening_id
    # Cancel.
    res2 = cancel_job_opening(w, player, opening_id)
    assert res2["ok"], res2
    assert not job_openings_for_employer(w, player)


# ───────────────────────── matching ─────────────────────────


def _player_with_funded_plot_in_town(w):
    player = PartyId("player")
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=10_000_000,  # $100k for wages
    )
    # Claim a plot adjacent to the first town.
    town = next(iter(w.towns.values()))
    center = w.plots[town.center_plot]
    pid: PlotId | None = None
    for p in w.plots.values():
        if p.owner is not None:
            continue
        if p.terrain in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW):
            continue
        if max(abs(p.x - center.x), abs(p.y - center.y)) <= 8:
            pid = p.plot_id
            break
    assert pid is not None, "no unowned plot near town center"
    assert claim_plot(w, player, pid)["ok"]
    return player, pid, town


def test_unemployed_laborer_in_town_takes_local_job_at_day_boundary():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, pid, town = _player_with_funded_plot_in_town(w)
    # Pick an unemployed laborer from this town.
    target_lab = next(
        lab
        for lab in w.laborers.values()
        if lab.home_town == town.town_id and lab.employer is None
    )
    res = post_job_opening(w, player, pid, skill_min=0, wage_per_day_cents=1000)
    assert res["ok"], res
    # Fire the matcher at a game-day boundary.
    w.tick = TICKS_PER_GAME_DAY
    matched = tick_job_market(w)
    assert matched["hired"] >= 1
    # Our target laborer (or another from the town) ended up employed.
    assert any(
        lab.employer == player
        for lab in w.laborers.values()
        if lab.home_town == town.town_id
    )


def test_job_market_does_not_run_off_boundary():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, pid, town = _player_with_funded_plot_in_town(w)
    post_job_opening(w, player, pid, skill_min=0, wage_per_day_cents=1000)
    w.tick = 100  # not a game-day boundary
    matched = tick_job_market(w)
    assert matched["hired"] == 0


def test_skill_gate_blocks_unqualified_laborer():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, pid, town = _player_with_funded_plot_in_town(w)
    # Force every unemployed laborer's skill below the threshold.
    for lab in w.laborers.values():
        if lab.home_town == town.town_id and lab.employer is None:
            lab.skill_level = 3
    res = post_job_opening(w, player, pid, skill_min=10, wage_per_day_cents=1500)
    assert res["ok"], res
    w.tick = TICKS_PER_GAME_DAY
    matched = tick_job_market(w)
    # No qualified laborer near this plot.
    assert matched["hired"] == 0
    # Lift one laborer's skill to qualify.
    lab = next(
        lab
        for lab in w.laborers.values()
        if lab.home_town == town.town_id and lab.employer is None
    )
    lab.skill_level = 12
    w.tick += TICKS_PER_GAME_DAY
    matched = tick_job_market(w)
    assert matched["hired"] >= 1


def test_laborer_too_far_cannot_apply():
    """A laborer outside the search radius (and not in the opening's town)
    is ineligible — verify the specific far laborer never gets the job."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, pid, town_a = _player_with_funded_plot_in_town(w)
    res = post_job_opening(w, player, pid, skill_min=0, wage_per_day_cents=1500)
    assert res["ok"], res
    # Find a laborer in a different town far away.
    town_a_isl = town_a.island_id
    far_town = next(
        t for t in w.towns.values() if t.island_id != town_a_isl
    )
    far_lab = next(
        lab
        for lab in w.laborers.values()
        if lab.home_town == far_town.town_id and lab.employer is None
    )
    plot_op = w.plots[pid]
    plot_lab = w.plots[far_lab.home_plot_id]
    d = max(abs(plot_op.x - plot_lab.x), abs(plot_op.y - plot_lab.y))
    assert d > JOB_SEARCH_RADIUS_TILES
    w.tick = TICKS_PER_GAME_DAY
    tick_job_market(w)
    # The specific far laborer must not have been hired by the player.
    assert far_lab.employer != player, (
        f"far laborer at distance {d} should not be eligible for an opening "
        f"with search radius {JOB_SEARCH_RADIUS_TILES}"
    )


# ───────────────────────── wages ─────────────────────────


def test_daily_wage_transfers_real_cents_via_ledger():
    """Wages are a real ledger transfer; conservation holds exactly."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, pid, town = _player_with_funded_plot_in_town(w)
    post_job_opening(w, player, pid, skill_min=0, wage_per_day_cents=1000)
    w.tick = TICKS_PER_GAME_DAY
    tick_job_market(w)
    # Pick the newly hired laborer.
    hired = next(
        lab for lab in w.laborers.values() if lab.employer == player
    )
    pre_player = w.ledger.balance(party_cash_account(player))
    pre_lab = w.ledger.balance(laborer_cash_account(hired.laborer_id))
    pre_total = w.ledger.total_cents()
    # Bump to the next day boundary so wages fire.
    w.tick += TICKS_PER_GAME_DAY
    wages = tick_laborer_wages(w)
    assert wages["paid"] >= 1
    post_player = w.ledger.balance(party_cash_account(player))
    post_lab = w.ledger.balance(laborer_cash_account(hired.laborer_id))
    assert pre_player - post_player == 1000
    assert post_lab - pre_lab == 1000
    assert w.ledger.total_cents() == pre_total


def test_insolvent_employer_loses_laborer_on_missed_wage():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, pid, town = _player_with_funded_plot_in_town(w)
    post_job_opening(w, player, pid, skill_min=0, wage_per_day_cents=999_999_999)
    w.tick = TICKS_PER_GAME_DAY
    tick_job_market(w)
    hired = next(
        (lab for lab in w.laborers.values() if lab.employer == player), None
    )
    if hired is None:
        pytest.skip("no laborer hired by player this seed")
    # Drain the player's cash so the next wage attempt fails.
    bal = w.ledger.balance(party_cash_account(player))
    if bal > 0:
        w.ledger.transfer(
            debit=party_cash_account(player),
            credit=system_reserve_account(),
            amount_cents=bal,
        )
    w.tick += TICKS_PER_GAME_DAY
    wages = tick_laborer_wages(w)
    assert wages["quit_for_nonpayment"] >= 1
    assert hired.employer is None
    assert hired.employment_contract is None


# ───────────────────────── unemployment pressure ─────────────────────────


def test_unemployed_laborer_does_not_receive_wages():
    """The wage tap only opens when there's an employer. Unemployed
    laborers receive zero cents from the wage tick."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    lab = next(l for l in w.laborers.values() if l.employer is None)
    pre = w.ledger.balance(laborer_cash_account(lab.laborer_id))
    w.tick = TICKS_PER_GAME_DAY * 2
    tick_laborer_wages(w)
    post = w.ledger.balance(laborer_cash_account(lab.laborer_id))
    assert pre == post


def test_only_employed_laborers_get_wages_in_a_single_tick():
    """When the wage tick fires, employed laborers receive their
    wage and unemployed laborers do not — verified per-account."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, pid, town = _player_with_funded_plot_in_town(w)
    post_job_opening(w, player, pid, skill_min=0, wage_per_day_cents=750)
    w.tick = TICKS_PER_GAME_DAY
    tick_job_market(w)
    employed = [lab for lab in w.laborers.values() if lab.employer == player]
    unemployed = [lab for lab in w.laborers.values() if lab.employer is None]
    if not employed:
        pytest.skip("no laborer matched this seed; covered elsewhere")
    pre_emp = {l.laborer_id: w.ledger.balance(laborer_cash_account(l.laborer_id)) for l in employed}
    sample_unemp = unemployed[:5]
    pre_unemp = {l.laborer_id: w.ledger.balance(laborer_cash_account(l.laborer_id)) for l in sample_unemp}
    w.tick += TICKS_PER_GAME_DAY
    tick_laborer_wages(w)
    for l in employed:
        post = w.ledger.balance(laborer_cash_account(l.laborer_id))
        assert post - pre_emp[l.laborer_id] == 750
    for l in sample_unemp:
        post = w.ledger.balance(laborer_cash_account(l.laborer_id))
        assert post == pre_unemp[l.laborer_id]

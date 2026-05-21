"""Settler job postings, matching, wages, and skill growth."""

from __future__ import annotations

from realm.actions.plot_actions import claim_plot
from realm.actions.blueprint_actions import build_on_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.genesis.settler_upgrades import _maybe_post_job_openings
from realm.population.employment import (
    post_job_opening,
    tick_job_market,
    tick_laborer_wages,
)
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def _first_settler(w: object) -> PartyId:
    return PartyId(sorted(p for p in w.parties if str(p).startswith("settler_"))[0])


def _unowned_land_plot(w: object) -> PlotId:
    return PlotId(
        next(
            p
            for p, pl in w.plots.items()
            if pl.owner is None and "water" not in str(pl.terrain).lower()
        )
    )


def test_settler_posts_job_for_active_building() -> None:
    w = bootstrap_genesis(seed=1, settler_count=5)
    player = _first_settler(w)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=5_000_000,
    )
    pid = _unowned_land_plot(w)
    assert claim_plot(w, player, pid)["ok"]
    res = build_on_plot(w, player, pid, "wood_shop", build_mode="turnkey")
    assert res["ok"], res
    complete_at = int(res.get("completes_at_tick", 0)) + 1
    for _ in range(max(complete_at + 50, 500)):
        advance_tick(w)
    _maybe_post_job_openings(w, player)
    assert any(
        op.employer == player and str(op.plot_id) == str(pid)
        for op in w.job_openings
    ), "Settler should have a job opening on the workshop plot"


def test_laborer_fills_job_opening() -> None:
    w = bootstrap_genesis(seed=2, settler_count=5)
    employer = _first_settler(w)
    town = next(iter(w.towns.values()))
    center = w.plots[town.center_plot]
    pid = PlotId(
        next(
            p
            for p, pl in w.plots.items()
            if pl.owner is None
            and "water" not in str(pl.terrain).lower()
            and max(abs(pl.x - center.x), abs(pl.y - center.y)) <= 6
        )
    )
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(employer),
        amount_cents=5_000_000,
    )
    assert claim_plot(w, employer, pid)["ok"]
    r = post_job_opening(w, employer, pid, skill_min=0, wage_per_day_cents=800)
    assert r["ok"]
    w.tick = 1440
    stats = tick_job_market(w)
    assert stats["hired"] >= 1, stats
    employed = sum(1 for lab in w.laborers.values() if lab.employer == employer)
    assert employed >= 1, "At least one laborer should be hired"


def test_wage_payment_conserves_ledger() -> None:
    w = bootstrap_genesis(seed=3, settler_count=5)
    employer = _first_settler(w)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(employer),
        amount_cents=5_000_000,
    )
    pid = _unowned_land_plot(w)
    assert claim_plot(w, employer, pid)["ok"]
    post_job_opening(w, employer, pid, skill_min=0, wage_per_day_cents=800)
    w.tick = 1440
    tick_job_market(w)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    w.tick = 2880
    tick_laborer_wages(w)
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_fired_when_employer_bankrupt() -> None:
    w = bootstrap_genesis(seed=4, settler_count=5)
    employer = _first_settler(w)
    pid = _unowned_land_plot(w)
    assert claim_plot(w, employer, pid)["ok"]
    post_job_opening(w, employer, pid, wage_per_day_cents=800)
    w.tick = 1440
    tick_job_market(w)
    hired = next(l for l in w.laborers.values() if l.employer == employer)
    acct = party_cash_account(employer)
    bal = w.ledger.balance(acct)
    if bal > 0:
        w.ledger.transfer(
            debit=acct,
            credit=system_reserve_account(),
            amount_cents=bal,
        )
    w.tick = 2880
    tick_laborer_wages(w)
    assert hired.employer is None

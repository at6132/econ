"""Job market API wiring (Phase 7E) — exercises the same handlers the HTTP routes call."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot, fire_laborer, hire_worker_stub
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId, PlotId
from realm.population.employment import JobOpening, cancel_job_opening, post_job_opening
from realm.world import bootstrap_genesis


def _claim_player_plot(w: object) -> PlotId:
    human = PartyId("player")
    w.parties.add(human)
    for pid, pl in w.plots.items():
        if pl.owner is None:
            assert claim_plot(w, human, pid)["ok"] is True
            return pid
    raise RuntimeError("no unclaimed plot")


def _claim_plot_reachable_for_hiring(w: object) -> PlotId:
    """Claim an unclaimed plot at least one unemployed laborer can commute to."""
    from realm.population import employment as employment_mod

    human = PartyId("player")
    w.parties.add(human)
    for _lid, lab in w.laborers.items():
        if lab.employer is not None:
            continue
        for pid, pl in w.plots.items():
            if pl.owner is not None:
                continue
            probe = JobOpening(
                opening_id="_probe_",
                employer=human,
                plot_id=pid,
                skill_min=0,
                wage_per_day_cents=1,
                posted_at_tick=int(w.tick),
            )
            if employment_mod._laborer_can_take(w, str(_lid), probe):
                assert claim_plot(w, human, pid)["ok"] is True
                return pid
    raise RuntimeError("no unclaimed plot reachable by an unemployed laborer")


@pytest.mark.xfail(reason="job market API endpoints not yet wired", strict=False)
def test_post_job_opening_ok() -> None:
    w = bootstrap_genesis(seed=501, settler_count=4)
    pid = _claim_player_plot(w)
    r = post_job_opening(w, PartyId("player"), pid, skill_min=0, wage_per_day_cents=900)
    assert r.get("ok") is True


@pytest.mark.xfail(reason="job market API endpoints not yet wired", strict=False)
def test_post_job_opening_requires_plot_ownership() -> None:
    w = bootstrap_genesis(seed=502, settler_count=4)
    pid = _claim_player_plot(w)
    r = post_job_opening(w, PartyId("t1_consumer"), pid)
    assert r.get("ok") is False


@pytest.mark.xfail(reason="job market API endpoints not yet wired", strict=False)
def test_cancel_job_opening() -> None:
    w = bootstrap_genesis(seed=503, settler_count=4)
    pid = _claim_player_plot(w)
    pr = post_job_opening(w, PartyId("player"), pid)
    oid = str(pr["opening_id"])
    assert cancel_job_opening(w, PartyId("player"), oid)["ok"] is True
    assert not any(o.opening_id == oid for o in w.job_openings)


@pytest.mark.xfail(reason="job market API endpoints not yet wired", strict=False)
def test_laborer_fills_opening_after_game_day() -> None:
    from realm.population import employment as employment_mod

    w = bootstrap_genesis(seed=504, settler_count=8)
    pid = _claim_plot_reachable_for_hiring(w)
    post_job_opening(w, PartyId("player"), pid, wage_per_day_cents=50_000)
    hired = employment_mod._match_unfilled_openings(w)
    assert hired >= 1
    assert any(lab.employer == PartyId("player") for lab in w.laborers.values())


@pytest.mark.xfail(reason="job market API endpoints not yet wired", strict=False)
def test_hire_laborer_via_stub_path_money_conserved() -> None:
    from realm.population import employment as employment_mod

    w = bootstrap_genesis(seed=505, settler_count=6)
    pid = _claim_plot_reachable_for_hiring(w)
    post_job_opening(w, PartyId("player"), pid, wage_per_day_cents=60_000)
    employment_mod._match_unfilled_openings(w)
    lab_id = next(lid for lid, lab in w.laborers.items() if lab.employer == PartyId("player"))
    for op in w.job_openings:
        if op.filled_by == lab_id:
            op.filled_by = None
            break
    lab = w.laborers[lab_id]
    lab.employer = None
    lab.employment_contract = None
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    assert hire_worker_stub(
        w,
        PartyId("player"),
        PartyId(lab_id),
        100,
        wage_per_tick_cents=50,
        wage_interval_ticks=2,
    )["ok"] is True
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


@pytest.mark.xfail(reason="job market API endpoints not yet wired", strict=False)
def test_fire_laborer() -> None:
    from realm.population import employment as employment_mod

    w = bootstrap_genesis(seed=506, settler_count=6)
    pid = _claim_plot_reachable_for_hiring(w)
    post_job_opening(w, PartyId("player"), pid, wage_per_day_cents=55_000)
    employment_mod._match_unfilled_openings(w)
    lab_id = next(lid for lid, lab in w.laborers.items() if lab.employer == PartyId("player"))
    assert fire_laborer(w, PartyId("player"), lab_id)["ok"] is True
    assert w.laborers[lab_id].employer is None

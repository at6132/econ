"""Job openings free when laborer leaves the workforce."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import PartyId, PlotId
from realm.population.employment import post_job_opening
from realm.population.laborers import _kill_laborer
from realm.world import bootstrap_genesis


def test_kill_laborer_clears_filled_by_on_opening() -> None:
    w = bootstrap_genesis(seed=7, grid_width=48, grid_height=36, settler_count=4)
    assert w.laborers
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"]
    res = post_job_opening(w, player, pid, wage_per_day_cents=500)
    assert res["ok"]
    oid = res["opening_id"]
    lab = next(iter(w.laborers.values()))
    op = next(o for o in w.job_openings if o.opening_id == oid)
    op.filled_by = lab.laborer_id
    lab.employer = player
    _kill_laborer(w, lab, "test")
    assert op.filled_by is None

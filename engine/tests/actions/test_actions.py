from realm.actions import SURVEY_COST_CENTS, claim_plot, survey_plot
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world import bootstrap_frontier

from plot_helpers import claimable_land_plot_id


def test_claim_and_survey() -> None:
    w = bootstrap_frontier(seed=3, grid_width=4, grid_height=3)
    pid = claimable_land_plot_id(w, PartyId("player"))
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    cash = party_cash_account(PartyId("player"))
    before = w.ledger.balance(cash)
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    after = w.ledger.balance(cash)
    assert before - after == SURVEY_COST_CENTS
    assert w.plots[pid].surveyed is True


def test_survey_plot_conserves_ledger_total() -> None:
    w = bootstrap_frontier(seed=31, grid_width=8, grid_height=4)
    pid = claimable_land_plot_id(w, PartyId("player"))
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    total = w.ledger.total_cents()
    sys_before = w.ledger.balance(system_reserve_account())
    cash = party_cash_account(PartyId("player"))
    cash_before = w.ledger.balance(cash)
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    assert w.ledger.total_cents() == total
    assert w.ledger.balance(cash) == cash_before - SURVEY_COST_CENTS
    assert w.ledger.balance(system_reserve_account()) == sys_before + SURVEY_COST_CENTS

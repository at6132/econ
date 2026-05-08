from realm.actions import claim_plot, survey_plot
from realm.ids import PartyId, PlotId
from realm.ledger import party_cash_account
from realm.world import bootstrap_frontier


def test_claim_and_survey() -> None:
    w = bootstrap_frontier(seed=3, grid_width=4, grid_height=3)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    cash = party_cash_account(PartyId("player"))
    before = w.ledger.balance(cash)
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    after = w.ledger.balance(cash)
    assert before - after == 50_000
    assert w.plots[pid].surveyed is True

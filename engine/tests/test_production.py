"""Production: inputs at start, outputs after duration; money conservation."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account
from realm.production import start_production
from realm.tick import advance_tick
from realm.world import bootstrap_frontier


def test_sawmill_completes_after_duration_ticks() -> None:
    w = bootstrap_frontier(seed=1, grid_width=3, grid_height=2)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    cash0 = w.ledger.balance(party_cash_account(PartyId("player")))
    assert start_production(w, PartyId("player"), pid, "sawmill")["ok"] is True
    assert w.inventory.qty(PartyId("player"), MaterialId("timber")) == 8 - 2
    assert w.inventory.qty(PartyId("player"), MaterialId("electricity")) == 8 - 1
    cash1 = w.ledger.balance(party_cash_account(PartyId("player")))
    assert cash1 == cash0 - 500  # labor_cents on sawmill recipe
    advance_tick(w)
    assert len(w.active_production) == 1
    advance_tick(w)
    assert len(w.active_production) == 0
    assert w.inventory.qty(PartyId("player"), MaterialId("lumber")) == 1


def test_money_conserved_across_sawmill_run() -> None:
    w = bootstrap_frontier(seed=2, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    total0 = w.ledger.total_cents()
    assert start_production(w, PartyId("player"), pid, "sawmill")["ok"] is True
    advance_tick(w)
    advance_tick(w)
    assert w.ledger.total_cents() == total0


def test_rejects_second_production_same_plot() -> None:
    w = bootstrap_frontier(seed=3, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert start_production(w, PartyId("player"), pid, "coal_generator")["ok"] is True
    r = start_production(w, PartyId("player"), pid, "coal_generator")
    assert r["ok"] is False

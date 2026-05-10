"""Production: inputs at start, outputs after duration; money conservation."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account
from realm.production import start_production
from realm.tick import advance_tick
from realm.world import bootstrap_frontier


def test_sawmill_completes_after_duration_ticks() -> None:
    w = bootstrap_frontier(seed=1, grid_width=3, grid_height=2)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
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
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    total0 = w.ledger.total_cents()
    assert start_production(w, PartyId("player"), pid, "sawmill")["ok"] is True
    advance_tick(w)
    advance_tick(w)
    assert w.ledger.total_cents() == total0


def test_rejects_second_production_same_plot() -> None:
    w = bootstrap_frontier(seed=3, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    assert start_production(w, PartyId("player"), pid, "coal_generator")["ok"] is True
    r = start_production(w, PartyId("player"), pid, "coal_generator")
    assert r["ok"] is False


def test_tool_cache_reduces_recipe_labor_cash() -> None:
    from realm.buildings import build_on_plot

    w = bootstrap_frontier(seed=5, grid_width=3, grid_height=2)
    pid = PlotId("p-0-0")
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    assert build_on_plot(w, player, pid, "tool_cache")["ok"] is True
    cash0 = w.ledger.balance(party_cash_account(player))
    assert start_production(w, player, pid, "sawmill")["ok"] is True
    cash1 = w.ledger.balance(party_cash_account(player))
    assert cash1 == cash0 - 450  # 500¢ × 90% (tool_cache labor BPS)


def test_stub_hire_routes_part_of_labor_to_employee() -> None:
    from realm.actions import hire_worker_stub

    w = bootstrap_frontier(seed=4, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    player = PartyId("player")
    emp = PartyId("t1_timber_merchant")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    assert hire_worker_stub(w, player, emp, 500)["ok"] is True
    pc = party_cash_account(player)
    ec = party_cash_account(emp)
    cash_p0 = w.ledger.balance(pc)
    cash_e0 = w.ledger.balance(ec)
    total0 = w.ledger.total_cents()
    assert start_production(w, player, pid, "sawmill")["ok"] is True
    assert w.ledger.total_cents() == total0
    assert w.ledger.balance(pc) == cash_p0 - 500
    assert w.ledger.balance(ec) == cash_e0 + 200


def test_twist_rope_completes_and_conserves_ledger() -> None:
    w = bootstrap_frontier(seed=6, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    total0 = w.ledger.total_cents()
    t0 = w.inventory.qty(player, MaterialId("timber"))
    e0 = w.inventory.qty(player, MaterialId("electricity"))
    assert start_production(w, player, pid, "twist_rope")["ok"] is True
    assert w.inventory.qty(player, MaterialId("timber")) == t0 - 1
    assert w.inventory.qty(player, MaterialId("electricity")) == e0 - 1
    advance_tick(w)
    advance_tick(w)
    assert w.ledger.total_cents() == total0
    assert w.inventory.qty(player, MaterialId("rope")) == 3


def test_build_ladder_completes_and_conserves_ledger() -> None:
    w = bootstrap_frontier(seed=8, grid_width=2, grid_height=2)
    pid = PlotId("p-0-0")
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    w.inventory.add(player, MaterialId("lumber"), 4)
    w.inventory.add(player, MaterialId("rope"), 4)
    w.inventory.add(player, MaterialId("electricity"), 4)
    total0 = w.ledger.total_cents()
    assert start_production(w, player, pid, "build_ladder")["ok"] is True
    advance_tick(w)
    advance_tick(w)
    advance_tick(w)
    assert w.ledger.total_cents() == total0
    assert w.inventory.qty(player, MaterialId("ladder")) == 1
    assert w.inventory.qty(player, MaterialId("lumber")) == 2
    assert w.inventory.qty(player, MaterialId("rope")) == 2

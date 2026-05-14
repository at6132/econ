"""Phase 2 financial contract stubs — ledger + tick FSM."""

from __future__ import annotations

from realm.contracts.stubs import (
    accept_equity_stub,
    accept_loan_contract,
    accept_service_sub,
    propose_equity_stub,
    propose_loan_contract,
    propose_service_sub,
    repay_loan_contract,
)
from realm.core.ids import PartyId
from realm.contracts.social import propose_contract_stub
from realm.world.tick import advance_tick
from realm.world import bootstrap_frontier


def test_propose_memo_rejects_reserved_phase2_kinds() -> None:
    w = bootstrap_frontier(seed=60, grid_width=2, grid_height=2)
    r = propose_contract_stub(w, PartyId("player"), PartyId("t1_consumer"), "loan")
    assert r["ok"] is False


def test_loan_manual_repay_conserves_ledger_total() -> None:
    w = bootstrap_frontier(seed=61, grid_width=2, grid_height=2)
    lender, borrower = PartyId("player"), PartyId("t1_consumer")
    t0 = w.ledger.total_cents()
    pr = propose_loan_contract(w, lender, borrower, 10_000, 11_000, 20)
    assert pr["ok"] is True
    cid = str(pr["contract_id"])
    assert accept_loan_contract(w, borrower, cid)["ok"] is True
    assert repay_loan_contract(w, borrower, cid)["ok"] is True
    assert w.ledger.total_cents() == t0
    assert next(c for c in w.contracts if c["id"] == cid)["status"] == "repaid"


def test_loan_overdue_auto_settles_when_solvent() -> None:
    w = bootstrap_frontier(seed=62, grid_width=2, grid_height=2)
    lender, borrower = PartyId("player"), PartyId("t1_consumer")
    pr = propose_loan_contract(w, lender, borrower, 5_000, 5_500, 1)
    cid = str(pr["contract_id"])
    assert accept_loan_contract(w, borrower, cid)["ok"] is True
    advance_tick(w)
    advance_tick(w)
    row = next(c for c in w.contracts if c["id"] == cid)
    assert row["status"] == "repaid"


def test_loan_overdue_breach_when_insolvent() -> None:
    w = bootstrap_frontier(seed=63, grid_width=2, grid_height=2)
    lender, borrower = PartyId("player"), PartyId("t1_consumer")
    pr = propose_loan_contract(w, lender, borrower, 1_000, 50_000, 1)
    cid = str(pr["contract_id"])
    assert accept_loan_contract(w, borrower, cid)["ok"] is True
    advance_tick(w)
    advance_tick(w)
    row = next(c for c in w.contracts if c["id"] == cid)
    assert row["status"] == "breached"
    assert w.reputation[str(borrower)]["breached"] >= 1


def test_equity_stub_pays_dividends_until_complete() -> None:
    w = bootstrap_frontier(seed=64, grid_width=2, grid_height=2)
    issuer, investor = PartyId("player"), PartyId("t1_consumer")
    t0 = w.ledger.total_cents()
    pr = propose_equity_stub(w, issuer, investor, 3_000, 100, 3)
    cid = str(pr["contract_id"])
    assert accept_equity_stub(w, investor, cid)["ok"] is True
    for _ in range(4):
        advance_tick(w)
    assert w.ledger.total_cents() == t0
    row = next(c for c in w.contracts if c["id"] == cid)
    assert row["status"] == "completed"


def test_equity_stub_breaches_on_dividend_shortfall() -> None:
    w = bootstrap_frontier(seed=65, grid_width=2, grid_height=2)
    issuer, investor = PartyId("t1_timber_merchant"), PartyId("player")
    pr = propose_equity_stub(w, issuer, investor, 500, 9_999_999, 2)
    cid = str(pr["contract_id"])
    assert accept_equity_stub(w, investor, cid)["ok"] is True
    advance_tick(w)
    row = next(c for c in w.contracts if c["id"] == cid)
    assert row["status"] == "breached"


def test_service_sub_prepaid_then_expires() -> None:
    w = bootstrap_frontier(seed=66, grid_width=2, grid_height=2)
    provider, sub = PartyId("player"), PartyId("t1_consumer")
    t0 = w.ledger.total_cents()
    pr = propose_service_sub(w, provider, sub, 400, 3)
    cid = str(pr["contract_id"])
    assert accept_service_sub(w, sub, cid)["ok"] is True
    assert w.ledger.total_cents() == t0
    advance_tick(w)
    advance_tick(w)
    advance_tick(w)
    advance_tick(w)
    row = next(c for c in w.contracts if c["id"] == cid)
    assert row["status"] == "expired"

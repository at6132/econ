"""Insurance, secondary loan market, and land-lease instruments."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.contracts.instruments import (
    TICKS_PER_7_GAME_DAYS,
    accept_insurance,
    accept_land_lease,
    buy_loan,
    list_loan_for_sale,
    propose_insurance,
    propose_land_lease,
    tick_insurance_payouts,
    tick_land_lease_contracts,
)
from realm.contracts.stubs import accept_loan_contract, propose_loan_contract
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId, PlotId
from realm.infrastructure.plot_access import party_may_operate_plot
from realm.population.laborers import TICKS_PER_GAME_DAY
from realm.world import bootstrap_frontier, bootstrap_genesis


def _claim_first(w: object, party: PartyId) -> PlotId:
    for pid, pl in w.plots.items():
        if pl.owner is None and claim_plot(w, party, pid)["ok"]:
            return pid
    raise RuntimeError("no claimable plot")


def test_insurance_premium_transfers_on_accept_conserved() -> None:
    w = bootstrap_genesis(seed=711, grid_width=8, grid_height=6, settler_count=2)
    ins = PartyId("frontier_insurance_co")
    insured = PartyId("player")
    pr = propose_insurance(
        w,
        ins,
        insured,
        "mine_collapse",
        None,
        payout_cents=50_000,
        premium_per_7days_cents=5_000,
        duration_ticks=TICKS_PER_7_GAME_DAYS * 3,
    )
    cid = str(pr["contract_id"])
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    assert accept_insurance(w, insured, cid)["ok"] is True
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_insurance_payout_on_mine_collapse_conserved() -> None:
    w = bootstrap_genesis(seed=712, grid_width=8, grid_height=6, settler_count=2)
    ins = PartyId("frontier_insurance_co")
    insured = PartyId("player")
    pid = _claim_first(w, insured)
    pr = propose_insurance(
        w,
        ins,
        insured,
        "mine_collapse",
        str(pid),
        payout_cents=12_000,
        premium_per_7days_cents=3_000,
        duration_ticks=TICKS_PER_7_GAME_DAYS * 4,
    )
    cid = str(pr["contract_id"])
    assert accept_insurance(w, insured, cid)["ok"] is True
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    w.tick = TICKS_PER_GAME_DAY
    w.event_log.append(
        {
            "kind": "mine_collapse",
            "tick": w.tick,
            "party": str(insured),
            "plot_id": str(pid),
        }
    )
    tick_insurance_payouts(w)
    c = next(x for x in w.contracts if x.get("id") == cid)
    assert c.get("status") == "paid_out"
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_insurance_does_not_pay_for_wrong_plot() -> None:
    w = bootstrap_genesis(seed=713, grid_width=8, grid_height=6, settler_count=2)
    ins = PartyId("frontier_insurance_co")
    insured = PartyId("player")
    p_ok = _claim_first(w, insured)
    p_bad = _claim_first(w, PartyId("settler_001"))
    pr = propose_insurance(
        w,
        ins,
        insured,
        "mine_collapse",
        str(p_ok),
        payout_cents=8_000,
        premium_per_7days_cents=2_000,
        duration_ticks=TICKS_PER_7_GAME_DAYS * 3,
    )
    cid = str(pr["contract_id"])
    assert accept_insurance(w, insured, cid)["ok"] is True
    w.tick = TICKS_PER_GAME_DAY
    w.event_log.append(
        {
            "kind": "mine_collapse",
            "tick": w.tick,
            "party": str(insured),
            "plot_id": str(p_bad),
        }
    )
    tick_insurance_payouts(w)
    c = next(x for x in w.contracts if x.get("id") == cid)
    assert c.get("status") == "active"


def test_loan_listed_on_secondary_market() -> None:
    w = bootstrap_frontier(seed=721, grid_width=4, grid_height=3)
    lender = PartyId("player")
    borrower = PartyId("t1_consumer")
    pr = propose_loan_contract(w, lender, borrower, 10_000, 12_000, due_in_ticks=50_000)
    cid = str(pr["contract_id"])
    assert accept_loan_contract(w, borrower, cid)["ok"] is True
    assert list_loan_for_sale(w, lender, cid, ask_cents=9_000)["ok"] is True
    lm = w.scenario_state.get("loan_market", [])
    assert any(x.get("contract_id") == cid for x in lm)


def test_buy_loan_changes_lender_conserved() -> None:
    w = bootstrap_frontier(seed=722, grid_width=4, grid_height=3)
    lender = PartyId("player")
    borrower = PartyId("t1_consumer")
    buyer = PartyId("t1_lumber_buyer")
    pr = propose_loan_contract(w, lender, borrower, 5_000, 6_000, due_in_ticks=80_000)
    cid = str(pr["contract_id"])
    assert accept_loan_contract(w, borrower, cid)["ok"] is True
    assert list_loan_for_sale(w, lender, cid, ask_cents=2_000)["ok"] is True
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    assert buy_loan(w, buyer, cid)["ok"] is True
    c = next(x for x in w.contracts if x.get("id") == cid)
    assert c.get("lender") == str(buyer)
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_land_lease_grants_and_revokes_operate_rights() -> None:
    w = bootstrap_frontier(seed=731, grid_width=6, grid_height=5)
    lessor = PartyId("player")
    lessee = PartyId("t1_consumer")
    pid = _claim_first(w, lessor)
    pr = propose_land_lease(
        w,
        lessor,
        lessee,
        pid,
        rent_per_7days_cents=500,
        duration_ticks=20 * TICKS_PER_GAME_DAY,
    )
    cid = str(pr["contract_id"])
    assert accept_land_lease(w, lessee, cid)["ok"] is True
    assert party_may_operate_plot(w, lessee, pid) is True
    c = next(x for x in w.contracts if x.get("id") == cid)
    w.tick = int(c["expires_tick"]) + 1
    tick_land_lease_contracts(w)
    assert party_may_operate_plot(w, lessee, pid) is False


def test_rent_paid_every_7_days_conserved() -> None:
    w = bootstrap_frontier(seed=732, grid_width=6, grid_height=5)
    lessor = PartyId("player")
    lessee = PartyId("t1_consumer")
    pid = _claim_first(w, lessor)
    pr = propose_land_lease(
        w,
        lessor,
        lessee,
        pid,
        rent_per_7days_cents=400,
        duration_ticks=30 * TICKS_PER_GAME_DAY,
    )
    cid = str(pr["contract_id"])
    assert accept_land_lease(w, lessee, cid)["ok"] is True
    c = next(x for x in w.contracts if x.get("id") == cid)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    w.tick = int(c["next_rent_tick"])
    tick_land_lease_contracts(w)
    assert_money_conserved(w.ledger, snap.ledger_total_cents)

"""Sprint 5 — Phase C tests: NPC bank, loan lifecycle, reputation pricing."""

from __future__ import annotations

import pytest

from realm.genesis.bank import (
    BANK_STARTING_CASH_CENTS,
    FIRST_BANK_PARTY_ID,
    LOAN_CYCLE_TICKS,
    active_loans_for_borrower,
    apply_bank_loan,
    bank_rates_view,
    cycle_payment_cents,
    rate_tier_for_reputation,
    repay_bank_loan,
    tick_bank_loans,
)
from realm.economy.exchange import (
    GENESIS_EXCHANGE_PARTY_ID,
    apply_exchange_reputation_adjustment,
    exchange_price_for_party,
)
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world import bootstrap_genesis


@pytest.fixture
def gen_world():
    return bootstrap_genesis(seed=750, grid_width=12, grid_height=10, settler_count=4)


def _give_cash(w, party, cents):
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=int(cents))


def test_bank_exists_at_bootstrap(gen_world) -> None:
    w = gen_world
    assert FIRST_BANK_PARTY_ID in w.parties
    bal = w.ledger.balance(party_cash_account(FIRST_BANK_PARTY_ID))
    assert bal == BANK_STARTING_CASH_CENTS
    bank_plot = w.scenario_state.get("bank_plot")
    assert bank_plot
    assert w.plots[PlotId(str(bank_plot))].owner == FIRST_BANK_PARTY_ID
    has_bank_building = any(
        b.get("building_id") == "bank_building"
        and b.get("plot_id") == bank_plot
        for b in w.plot_buildings
    )
    assert has_bank_building


def test_loan_apply_and_disburse(gen_world) -> None:
    w = gen_world
    player = PartyId("player")
    w.parties.add(player)
    w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    starting_total = w.ledger.total_cents()
    bank_before = w.ledger.balance(party_cash_account(FIRST_BANK_PARTY_ID))
    player_before = w.ledger.balance(party_cash_account(player))
    r = apply_bank_loan(w, player, 200_000, 3)
    assert r["ok"] is True
    assert (
        w.ledger.balance(party_cash_account(player)) == player_before + 200_000
    )
    assert (
        w.ledger.balance(party_cash_account(FIRST_BANK_PARTY_ID)) == bank_before - 200_000
    )
    assert w.ledger.total_cents() == starting_total
    loans = active_loans_for_borrower(w, player)
    assert len(loans) == 1
    assert loans[0]["principal_cents"] == 200_000


def test_loan_repayment(gen_world) -> None:
    w = gen_world
    player = PartyId("player")
    w.parties.add(player)
    w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    r = apply_bank_loan(w, player, 200_000, 2)
    loan_id = r["loan_id"]
    loan = next(c for c in w.contracts if c.get("id") == loan_id)
    expected_payment = cycle_payment_cents(loan)
    bank_before = w.ledger.balance(party_cash_account(FIRST_BANK_PARTY_ID))
    starting_total = w.ledger.total_cents()
    r2 = repay_bank_loan(w, player, loan_id)
    assert r2["ok"] is True
    assert r2["payment_cents"] == expected_payment
    assert (
        w.ledger.balance(party_cash_account(FIRST_BANK_PARTY_ID))
        == bank_before + expected_payment
    )
    assert w.ledger.total_cents() == starting_total


def test_loan_default_claims_collateral(gen_world) -> None:
    w = gen_world
    player = PartyId("player")
    w.parties.add(player)
    w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    target_plot = None
    for pid, p in w.plots.items():
        if p.owner is None:
            p.owner = player
            target_plot = pid
            break
    assert target_plot is not None
    r = apply_bank_loan(w, player, 100_000, 3, collateral_plot_id=target_plot)
    assert r["ok"]
    # Drain the borrower so they cannot repay.
    drain = w.ledger.balance(party_cash_account(player))
    if drain > 0:
        w.ledger.transfer(
            debit=party_cash_account(player),
            credit=system_reserve_account(),
            amount_cents=drain,
        )
    # Advance two full cycles past due to trigger 2 misses.
    for _ in range(2):
        w.tick += LOAN_CYCLE_TICKS + 1
        tick_bank_loans(w)
    loan = next(c for c in w.contracts if c.get("id") == r["loan_id"])
    assert loan["status"] == "defaulted"
    assert w.plots[target_plot].owner == FIRST_BANK_PARTY_ID


def test_reputation_discount_on_exchange() -> None:
    base = 1000
    rep = {"honored": 12, "breached": 0}
    assert exchange_price_for_party(base, rep) == 950
    rep_high = {"honored": 30, "breached": 0}
    assert exchange_price_for_party(base, rep_high) == 920


def test_reputation_premium_on_exchange() -> None:
    base = 1000
    rep = {"honored": 1, "breached": 5}
    assert exchange_price_for_party(base, rep) == 1050


def test_reputation_neutral_on_exchange() -> None:
    base = 1000
    assert exchange_price_for_party(base, None) == base
    assert exchange_price_for_party(base, {"honored": 0, "breached": 0}) == base


def test_exchange_reputation_rebate_settles_through_ledger(gen_world) -> None:
    w = gen_world
    player = PartyId("player")
    w.parties.add(player)
    w.reputation[str(player)] = {"honored": 12, "breached": 0}
    _give_cash(w, player, 100_000)
    # Pre-fund the exchange so it can pay the rebate.
    _give_cash(w, GENESIS_EXCHANGE_PARTY_ID, 100_000)
    starting_total = w.ledger.total_cents()
    player_before = w.ledger.balance(party_cash_account(player))
    ex_before = w.ledger.balance(party_cash_account(GENESIS_EXCHANGE_PARTY_ID))
    apply_exchange_reputation_adjustment(w, player, fill_qty=10, fill_unit_price_cents=100)
    assert w.ledger.total_cents() == starting_total
    assert w.ledger.balance(party_cash_account(player)) == player_before + 50
    assert w.ledger.balance(party_cash_account(GENESIS_EXCHANGE_PARTY_ID)) == ex_before - 50


def test_bank_rate_tier_by_reputation() -> None:
    tier_starter = rate_tier_for_reputation(0)
    assert tier_starter["tier"] == "starter"
    assert tier_starter["rate_bps_per_cycle"] == 1200
    tier_mid = rate_tier_for_reputation(3)
    assert tier_mid["tier"] == "established"
    assert tier_mid["rate_bps_per_cycle"] == 800
    tier_top = rate_tier_for_reputation(15)
    assert tier_top["tier"] == "trusted"
    assert tier_top["rate_bps_per_cycle"] == 600


def test_bank_rejects_principal_over_tier_cap(gen_world) -> None:
    w = gen_world
    player = PartyId("player")
    w.parties.add(player)
    w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    r = apply_bank_loan(w, player, 5_000_000, 3)
    assert r["ok"] is False
    assert "cap" in r["reason"].lower()


def test_bank_rates_view_marks_current_tier(gen_world) -> None:
    w = gen_world
    player = PartyId("player")
    w.parties.add(player)
    w.reputation[str(player)] = {"honored": 4, "breached": 0}
    view = bank_rates_view(w, player)
    cur = [t for t in view["tiers"] if t["current_for_party"]]
    assert len(cur) == 1
    assert cur[0]["tier"] == "established"

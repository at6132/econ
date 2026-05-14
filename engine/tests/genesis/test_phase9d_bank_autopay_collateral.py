"""Phase 9D — bank-loan auto-deduct on due-tick + collateral requirement.

Closes audit findings B5.1 (loans had no auto-deduct; borrowers could
just sit on cash and accept reputation hits) and B5.2 (no tier required
collateral).

Tests prove:

* When a loan is due and the borrower has cash, ``tick_bank_loans``
  pulls the cycle payment automatically.
* When the borrower can't cover the payment, the cycle is recorded as
  missed (existing reputation + default path still works).
* The "trusted" tier requires a collateral plot at application time.
* Auto-paid cycles still cancel one prior miss and full repayment
  marks the loan repaid + bumps honored reputation.
"""

from __future__ import annotations

import pytest

from realm.genesis.bank import (
    BANK_RATE_TIERS,
    FIRST_BANK_PARTY_ID,
    LOAN_CYCLE_TICKS,
    apply_bank_loan,
    cycle_payment_cents,
    rate_tier_for_reputation,
    tick_bank_loans,
)
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world import bootstrap_genesis


@pytest.fixture
def gen_world():
    return bootstrap_genesis(seed=911, grid_width=12, grid_height=10, settler_count=4)


def _give_cash(w, party, cents):
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=int(cents))


def _seed_player(w):
    player = PartyId("player")
    w.parties.add(player)
    w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    return player


def _seed_player_with_plot(w):
    player = _seed_player(w)
    target_plot = None
    for pid, p in w.plots.items():
        if p.owner is None:
            p.owner = player
            target_plot = pid
            break
    assert target_plot is not None
    return player, target_plot


# ────────────────────────── auto-deduct ──────────────────────────


def test_auto_deduct_pulls_payment_when_borrower_has_cash(gen_world):
    w = gen_world
    player = _seed_player(w)
    r = apply_bank_loan(w, player, 200_000, num_cycles=3)
    assert r["ok"], r
    loan_id = r["loan_id"]
    loan = next(c for c in w.contracts if c.get("id") == loan_id)
    expected_payment = cycle_payment_cents(loan)
    bank_acct = party_cash_account(FIRST_BANK_PARTY_ID)
    player_acct = party_cash_account(player)
    bank_before = w.ledger.balance(bank_acct)
    player_before = w.ledger.balance(player_acct)
    # Jump to the due-tick + 1 and tick.
    w.tick = int(loan["next_due_tick"]) + 1
    tick_bank_loans(w)
    # Money moved borrower → lender automatically.
    bank_after = w.ledger.balance(bank_acct)
    player_after = w.ledger.balance(player_acct)
    assert bank_after - bank_before == expected_payment
    assert player_before - player_after == expected_payment
    loan_after = next(c for c in w.contracts if c.get("id") == loan_id)
    assert loan_after["payments_made"] == 1
    assert loan_after["status"] == "active"


def test_missed_payment_when_borrower_cannot_cover(gen_world):
    w = gen_world
    player = _seed_player(w)
    r = apply_bank_loan(w, player, 200_000, num_cycles=3)
    assert r["ok"]
    loan_id = r["loan_id"]
    # Drain the borrower so the auto-pay can't pull.
    bal = w.ledger.balance(party_cash_account(player))
    if bal > 0:
        w.ledger.transfer(
            debit=party_cash_account(player),
            credit=system_reserve_account(),
            amount_cents=bal,
        )
    w.tick = int(LOAN_CYCLE_TICKS) + 1
    tick_bank_loans(w)
    loan_after = next(c for c in w.contracts if c.get("id") == loan_id)
    assert loan_after["payments_made"] == 0
    assert loan_after["missed_payments"] == 1
    rep = w.reputation[str(player)]
    assert int(rep["breached"]) >= 1


def test_auto_deduct_repays_loan_in_full_and_bumps_reputation(gen_world):
    w = gen_world
    player = _seed_player(w)
    r = apply_bank_loan(w, player, 200_000, num_cycles=2)
    assert r["ok"]
    loan_id = r["loan_id"]
    loan = next(c for c in w.contracts if c.get("id") == loan_id)
    payment = cycle_payment_cents(loan)
    # Top up the borrower so they can definitely cover both cycles.
    _give_cash(w, player, payment * 4)
    rep_before = int(w.reputation[str(player)].get("honored", 0))
    # Tick across two due dates.
    for _ in range(2):
        w.tick = int(
            next(c for c in w.contracts if c.get("id") == loan_id)["next_due_tick"]
        ) + 1
        tick_bank_loans(w)
    loan_after = next(c for c in w.contracts if c.get("id") == loan_id)
    assert loan_after["status"] == "repaid"
    rep_after = int(w.reputation[str(player)].get("honored", 0))
    assert rep_after == rep_before + 1


def test_auto_deduct_cancels_one_prior_miss(gen_world):
    """A missed cycle is "recovered" when the next auto-pay succeeds."""
    w = gen_world
    player = _seed_player(w)
    r = apply_bank_loan(w, player, 200_000, num_cycles=4)
    loan_id = r["loan_id"]
    # Drain → miss cycle 1.
    bal = w.ledger.balance(party_cash_account(player))
    w.ledger.transfer(
        debit=party_cash_account(player),
        credit=system_reserve_account(),
        amount_cents=bal,
    )
    w.tick = LOAN_CYCLE_TICKS + 1
    tick_bank_loans(w)
    loan = next(c for c in w.contracts if c.get("id") == loan_id)
    assert loan["missed_payments"] == 1
    # Refill borrower → auto-pay cycle 2 → miss counter goes back to 0.
    _give_cash(w, player, 1_000_000)
    w.tick = int(loan["next_due_tick"]) + 1
    tick_bank_loans(w)
    loan_after = next(c for c in w.contracts if c.get("id") == loan_id)
    assert loan_after["payments_made"] == 1
    assert loan_after["missed_payments"] == 0


# ────────────────────────── collateral required ──────────────────────────


def test_trusted_tier_requires_collateral_at_application(gen_world):
    """A borrower with 10+ honored reps may take a bigger loan but only with
    collateral attached."""
    w = gen_world
    player = _seed_player(w)
    w.reputation[str(player)] = {"honored": 12, "breached": 0}
    tier = rate_tier_for_reputation(12)
    assert tier["tier"] == "trusted"
    assert bool(tier["requires_collateral"]) is True
    # Without collateral — refused.
    no_coll = apply_bank_loan(w, player, 1_500_000, num_cycles=4)
    assert not no_coll["ok"]
    assert "collateral" in no_coll["reason"].lower()


def test_trusted_tier_succeeds_with_collateral(gen_world):
    w = gen_world
    player, target_plot = _seed_player_with_plot(w)
    w.reputation[str(player)] = {"honored": 12, "breached": 0}
    res = apply_bank_loan(
        w, player, 1_500_000, num_cycles=4, collateral_plot_id=target_plot
    )
    assert res["ok"], res
    assert res["tier"] == "trusted"


def test_starter_and_established_tiers_still_unsecured(gen_world):
    """Lower tiers don't need collateral so first-time borrowers can still
    bootstrap a business."""
    w = gen_world
    player = _seed_player(w)
    starter = apply_bank_loan(w, player, 100_000, num_cycles=2)
    assert starter["ok"], starter
    w.reputation[str(player)] = {"honored": 5, "breached": 0}
    est = apply_bank_loan(w, player, 600_000, num_cycles=3)
    assert est["ok"], est


def test_collateral_required_check_doesnt_break_with_override():
    """``rate_bps_override`` shouldn't be a back-door around the collateral gate."""
    w = bootstrap_genesis(seed=912, grid_width=12, grid_height=10, settler_count=4)
    player = _seed_player(w)
    w.reputation[str(player)] = {"honored": 12, "breached": 0}
    res = apply_bank_loan(
        w, player, 1_500_000, num_cycles=4, rate_bps_override=400
    )
    assert not res["ok"]
    assert "collateral" in res["reason"].lower()

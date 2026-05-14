"""Phase 9H — Order-book sanity: re-quote dampener.

Audit finding: Tier 2 agents would cancel and re-post resting orders
every cadence even when the price hadn't moved, resetting time-priority
and burying player orders. The dampener now requires both a price
movement (>= REQUOTE_MIN_DELTA_CENTS) AND a cooldown
(REQUOTE_COOLDOWN_TICKS) before the cancel + re-post fires.
"""

from __future__ import annotations

import pytest

from realm.agents.requote_dampener import (
    CANCEL_FEE_CENTS,
    REQUOTE_COOLDOWN_TICKS,
    REQUOTE_MIN_DELTA_CENTS,
    charge_cancel_fee,
    record_requote,
    should_requote,
)
from realm.agents.tier2 import tick_tier2_agents
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.economy.markets import place_buy_order, place_sell_order
from realm.world.world import bootstrap_frontier


@pytest.fixture
def gen_world():
    """Tier 2 agents only exist in the frontier bootstrap (genesis is co-founder mode)."""
    return bootstrap_frontier(seed=42, grid_width=48, grid_height=36)


# ─────────── should_requote: no resting -> True ───────────


def test_should_requote_true_when_no_resting_orders(gen_world):
    w = gen_world
    party = PartyId("t2_lumber_bid")
    if party not in w.parties:
        pytest.skip("tier2 agent not seeded")
    # Bootstrap doesn't pre-post for this party.
    mat = MaterialId("lumber")
    assert should_requote(w, party, mat, "bid", 100) is True


# ─────────── price-movement gate ───────────


def test_should_requote_false_when_price_unchanged(gen_world):
    w = gen_world
    party = PartyId("t2_lumber_bid")
    if party not in w.parties:
        pytest.skip("tier2 agent not seeded")
    mat = MaterialId("lumber")
    # Seed cash + a resting order so the gate has something to test.
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=1_000_00,
    )
    place_buy_order(w, party, mat, 1, 50)
    record_requote(w, party, mat, "bid", 50)
    # Advance past cooldown.
    w.tick += REQUOTE_COOLDOWN_TICKS + 1
    # Same intended price -> no churn.
    assert should_requote(w, party, mat, "bid", 50) is False
    # Tiny jitter inside the delta band -> still no churn.
    assert (
        should_requote(w, party, mat, "bid", 50 + REQUOTE_MIN_DELTA_CENTS - 1) is False
    )
    # Real move -> allowed.
    assert (
        should_requote(w, party, mat, "bid", 50 + REQUOTE_MIN_DELTA_CENTS) is True
    )


# ─────────── cooldown gate ───────────


def test_should_requote_false_inside_cooldown(gen_world):
    w = gen_world
    party = PartyId("t2_lumber_bid")
    if party not in w.parties:
        pytest.skip("tier2 agent not seeded")
    mat = MaterialId("lumber")
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=1_000_00,
    )
    place_buy_order(w, party, mat, 1, 50)
    record_requote(w, party, mat, "bid", 50)
    # Still inside cooldown -- even a big price move should be blocked.
    w.tick += REQUOTE_COOLDOWN_TICKS - 1
    assert should_requote(w, party, mat, "bid", 75) is False


# ─────────── cancel fee charges ───────────


def test_cancel_fee_drains_to_reserve_per_cancel(gen_world):
    w = gen_world
    party = PartyId("t2_lumber_bid")
    if party not in w.parties:
        pytest.skip("tier2 agent not seeded")
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=10_000,
    )
    cash_before = w.ledger.balance(party_cash_account(party))
    reserve_before = w.ledger.balance(system_reserve_account())
    paid = charge_cancel_fee(w, party, 3)
    assert paid == 3 * CANCEL_FEE_CENTS
    assert w.ledger.balance(party_cash_account(party)) == cash_before - paid
    assert w.ledger.balance(system_reserve_account()) == reserve_before + paid


def test_cancel_fee_silent_noop_when_no_cash(gen_world):
    w = gen_world
    party = PartyId("t2_lumber_bid")
    if party not in w.parties:
        pytest.skip("tier2 agent not seeded")
    # Strip all cash first.
    src = party_cash_account(party)
    bal = w.ledger.balance(src)
    if bal > 0:
        w.ledger.transfer(
            debit=src, credit=system_reserve_account(), amount_cents=bal
        )
    paid = charge_cancel_fee(w, party, 5)
    assert paid == 0


# ─────────── end-to-end: tier2 agents don't churn the book ───────────


def test_tier2_does_not_repost_when_market_is_quiet(gen_world):
    """Run tick_tier2_agents repeatedly across a quiet market and
    verify the t2_ele_bidstack agent only re-posts once per real price
    change."""
    w = gen_world
    party = PartyId("t2_ele_bidstack")
    if party not in w.parties:
        pytest.skip("tier2 agent not seeded")
    mat = MaterialId("electricity")
    # Seed cash so the agent can keep posting / paying microfees.
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=1_000_00,
    )
    # First run -> the agent posts (no prior state).
    w.tick = 20
    tick_tier2_agents(w)
    bids_after_first = [
        b for b in w.market_bids_by_material.get(str(mat), []) if b.party == party
    ]
    # Run 50 more cycles WITHOUT changing the world: same RNG namespace
    # means the agent will produce nearly-identical limit prices, so the
    # dampener should suppress most cancels.
    cancel_events = 0
    for cycle in range(2, 50):
        w.tick = 20 * cycle
        tick_tier2_agents(w)
        for evt in w.event_log[-20:]:
            ec = evt.get("event_class") if isinstance(evt, dict) else getattr(evt, "event_class", "")
            if ec == "market_order_cancelled":
                cancel_events += 1
    # Even though we ran the agent 49 times, the dampener should have
    # blocked the vast majority of cancels. Bound it loosely: fewer than
    # 25 cancel events across 49 runs (vs. ~49 before the dampener).
    assert cancel_events < 25, f"too many cancels: {cancel_events}"


def test_dampener_state_persists_in_scenario_state(gen_world):
    w = gen_world
    party = PartyId("t2_clay_sweep")
    mat = MaterialId("clay")
    record_requote(w, party, mat, "ask", 99)
    state = w.scenario_state.get("agent_quote_state") or {}
    key = f"{party}|{mat}|ask"
    assert key in state
    assert state[key]["last_price"] == 99
    assert state[key]["last_tick"] == int(w.tick)

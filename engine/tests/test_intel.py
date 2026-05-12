"""Law 6 — paid market history visibility."""

from __future__ import annotations

from realm.ids import PartyId
from realm.intel import MARKET_INTEL_EXTEND_TICKS, MARKET_INTEL_FEE_CENTS, FREE_MARKET_HISTORY_TICKS, purchase_market_intel
from realm.ledger import party_cash_account, system_reserve_account
from realm.world import bootstrap_frontier, world_public_dict


def test_purchase_intel_transfers_fee_and_extends_expiry() -> None:
    w = bootstrap_frontier(seed=11, grid_width=2, grid_height=2)
    w.tick = 40
    total = w.ledger.total_cents()
    party = PartyId("player")
    acct = party_cash_account(party)
    before = w.ledger.balance(acct)
    sys_before = w.ledger.balance(system_reserve_account())
    r = purchase_market_intel(w, party)
    assert r["ok"] is True
    assert w.ledger.total_cents() == total
    assert w.ledger.balance(acct) == before - MARKET_INTEL_FEE_CENTS
    assert w.ledger.balance(system_reserve_account()) == sys_before + MARKET_INTEL_FEE_CENTS
    assert w.market_intel_expires_tick == 40 + MARKET_INTEL_EXTEND_TICKS


def test_world_public_full_vs_truncated_market_history() -> None:
    w = bootstrap_frontier(seed=12, grid_width=2, grid_height=2)
    w.market_history = [
        {"tick": i, "best_asks_cents": {"grain": 120}, "best_bids_cents": {}} for i in range(300)
    ]
    w.tick = 500
    w.market_intel_expires_tick = 0
    pub_free = world_public_dict(w)
    assert pub_free["market_intel_active"] is False
    assert len(pub_free["market_history"]) == 160

    w.market_intel_expires_tick = 600
    pub_full = world_public_dict(w)
    assert pub_full["market_intel_active"] is True
    assert len(pub_full["market_history"]) == 160

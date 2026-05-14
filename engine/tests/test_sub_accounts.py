"""Sprint 5 — Phase B tests: sub-accounts, transfer_own, 7-day P&L."""

from __future__ import annotations

from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account
from realm.sub_accounts import (
    PNL_WINDOW_TICKS,
    PRIMARY_LABEL,
    account_id_for,
    create_sub_account,
    log_sub_account_tx,
    party_accounts_view,
    party_sub_account_labels,
    sub_account_pnl_7day,
    transfer_own,
)
from realm.world import bootstrap_frontier


def test_create_sub_account() -> None:
    w = bootstrap_frontier(seed=700, grid_width=4, grid_height=3)
    player = PartyId("player")
    r = create_sub_account(w, player, "reserve")
    assert r["ok"] is True
    assert r["label"] == "reserve"
    assert r["balance_cents"] == 0
    assert "reserve" in party_sub_account_labels(w, player)
    acct = account_id_for(player, "reserve")
    assert w.ledger.balance(acct) == 0


def test_create_sub_account_idempotent_and_validation() -> None:
    w = bootstrap_frontier(seed=701, grid_width=4, grid_height=3)
    player = PartyId("player")
    r1 = create_sub_account(w, player, "shipping")
    assert r1["ok"] is True
    r2 = create_sub_account(w, player, "shipping")
    assert r2["ok"] is True and r2.get("already_exists") is True
    bad = create_sub_account(w, player, "cash")
    assert bad["ok"] is False
    bad2 = create_sub_account(w, player, "a")
    assert bad2["ok"] is False
    bad3 = create_sub_account(w, player, "with space")
    assert bad3["ok"] is False


def test_transfer_between_own_accounts() -> None:
    w = bootstrap_frontier(seed=702, grid_width=4, grid_height=3)
    player = PartyId("player")
    create_sub_account(w, player, "reserve")
    starting_total = w.ledger.total_cents()
    cash_before = w.ledger.balance(party_cash_account(player))
    r = transfer_own(w, player, "cash", "reserve", 500)
    assert r["ok"] is True
    assert (
        w.ledger.balance(party_cash_account(player)) == cash_before - 500
    )
    assert (
        w.ledger.balance(account_id_for(player, "reserve")) == 500
    )
    assert w.ledger.total_cents() == starting_total


def test_transfer_own_rejects_unknown_label_and_insufficient_funds() -> None:
    w = bootstrap_frontier(seed=703, grid_width=4, grid_height=3)
    player = PartyId("player")
    r_missing = transfer_own(w, player, "cash", "no_such_label", 100)
    assert r_missing["ok"] is False
    create_sub_account(w, player, "reserve")
    huge = w.ledger.balance(party_cash_account(player)) + 1_000_000
    r_broke = transfer_own(w, player, "cash", "reserve", huge)
    assert r_broke["ok"] is False
    assert "insufficient" in r_broke["reason"].lower()


def test_sub_account_7day_pnl() -> None:
    w = bootstrap_frontier(seed=704, grid_width=4, grid_height=3)
    player = PartyId("player")
    create_sub_account(w, player, "shipping")
    transfer_own(w, player, "cash", "shipping", 400)
    w.tick += 200
    transfer_own(w, player, "cash", "shipping", 250)
    w.tick += 200
    transfer_own(w, player, "shipping", "cash", 150)
    pnl = sub_account_pnl_7day(w, player, "shipping")
    assert pnl["credits_cents"] == 400 + 250
    assert pnl["debits_cents"] == 150
    assert pnl["net_cents"] == 500
    # Old row outside window should not count.
    log_sub_account_tx(
        w, account_id_for(player, "shipping"), delta_cents=1000, kind="ancient", counterparty=None
    )
    rows = w.scenario_state["sub_account_history"][str(account_id_for(player, "shipping"))]
    rows[-1]["tick"] = int(w.tick) - PNL_WINDOW_TICKS - 1
    pnl_after = sub_account_pnl_7day(w, player, "shipping")
    assert pnl_after["credits_cents"] == 400 + 250


def test_primary_account_always_exists() -> None:
    w = bootstrap_frontier(seed=705, grid_width=4, grid_height=3)
    player = PartyId("player")
    accounts = party_accounts_view(w, player)
    primaries = [a for a in accounts if a["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["label"] == PRIMARY_LABEL
    new_party = PartyId("brand_new")
    w.parties.add(new_party)
    accounts2 = party_accounts_view(w, new_party)
    assert any(a["is_primary"] and a["label"] == PRIMARY_LABEL for a in accounts2)

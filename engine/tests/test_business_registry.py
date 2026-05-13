"""Sprint 5 — Phase A tests: business registration + display names everywhere."""

from __future__ import annotations

from realm.actions import (
    BUSINESS_REGISTRATION_FEE_CENTS,
    register_business,
)
from realm.ids import MaterialId, PartyId
from realm.ledger import party_cash_account, system_reserve_account
from realm.markets import place_sell_order
from realm.world import World, bootstrap_frontier


def _give_cash(w: World, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=acct, amount_cents=cents
    )


def test_register_business_updates_display_name() -> None:
    w = bootstrap_frontier(seed=600, grid_width=4, grid_height=3)
    player = PartyId("player")
    r = register_business(w, player, "Northern Iron Co.", "we sell iron")
    assert r["ok"] is True
    assert w.party_display_names[str(player)] == "Northern Iron Co."
    rec = w.business_registry[str(player)]
    assert rec.business_name == "Northern Iron Co."
    assert rec.description == "we sell iron"
    assert rec.registered_at_tick == w.tick


def test_register_business_deducts_fee() -> None:
    w = bootstrap_frontier(seed=601, grid_width=4, grid_height=3)
    player = PartyId("player")
    starting_total = w.ledger.total_cents()
    cash_before = w.ledger.balance(party_cash_account(player))
    r = register_business(w, player, "Acme Logging", "")
    assert r["ok"] is True
    assert (
        w.ledger.balance(party_cash_account(player))
        == cash_before - BUSINESS_REGISTRATION_FEE_CENTS
    )
    assert w.ledger.total_cents() == starting_total


def test_duplicate_name_rejected() -> None:
    w = bootstrap_frontier(seed=602, grid_width=4, grid_height=3)
    player = PartyId("player")
    other = PartyId("rival_co")
    w.parties.add(other)
    w.reputation.setdefault(str(other), {"honored": 0, "breached": 0})
    _give_cash(w, other, 50_000)
    r1 = register_business(w, player, "Frontier Holdings", "")
    assert r1["ok"] is True
    r2 = register_business(w, other, "Frontier Holdings", "")
    assert r2["ok"] is False
    assert "taken" in r2.get("reason", "").lower()


def test_business_name_in_market_listing() -> None:
    """After registration, market events show the business name as seller via
    ``party_display_names``. The engine doesn't store a separate "seller name"
    field — it consults the display-name map at render time, which is exactly
    what the spec asks for."""
    w = bootstrap_frontier(seed=603, grid_width=4, grid_height=3)
    player = PartyId("player")
    register_business(w, player, "Player Mill Ltd", "")
    # Player has timber from bootstrap; place an ask.
    r = place_sell_order(w, player, MaterialId("timber"), 1, 80)
    assert r.get("ok"), r
    # The display-name lookup is what every UI / feed call uses.
    label = w.party_display_names.get(str(player))
    assert label == "Player Mill Ltd"


def test_invalid_name_rejected() -> None:
    w = bootstrap_frontier(seed=604, grid_width=4, grid_height=3)
    player = PartyId("player")
    for bad in ("", "ab", "x" * 41, "@badname", "name\twith\ttab"):
        r = register_business(w, player, bad, "")
        assert r["ok"] is False, f"expected reject for {bad!r}"


def test_idempotent_same_name_same_party() -> None:
    w = bootstrap_frontier(seed=605, grid_width=4, grid_height=3)
    player = PartyId("player")
    r1 = register_business(w, player, "Quiet Iron", "")
    assert r1["ok"] is True
    cash_after_first = w.ledger.balance(party_cash_account(player))
    r2 = register_business(w, player, "Quiet Iron", "")
    assert r2["ok"] is True
    assert r2.get("already_registered") is True
    # No double-fee on a no-op re-register.
    assert w.ledger.balance(party_cash_account(player)) == cash_after_first

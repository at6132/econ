"""Player starting cash helpers."""

from __future__ import annotations

from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.player_economy import (
    PLAYER_STARTING_CASH_CENTS,
    ensure_player_starting_cash,
)
from realm.world import bootstrap_genesis


def test_ensure_player_starting_cash_tops_up_short_seed() -> None:
    world = bootstrap_genesis(seed=7)
    player = PartyId("player")
    acct = party_cash_account(player)
    # Simulate stale bootstrap ($10k).
    world.ledger.transfer(
        debit=acct,
        credit=system_reserve_account(),
        amount_cents=PLAYER_STARTING_CASH_CENTS - 1_000_000,
    )
    assert int(world.ledger.balance(acct)) == 1_000_000
    topped = ensure_player_starting_cash(world)
    assert topped == PLAYER_STARTING_CASH_CENTS


def test_ensure_player_starting_cash_idempotent_at_target() -> None:
    world = bootstrap_genesis(seed=8)
    assert ensure_player_starting_cash(world) == PLAYER_STARTING_CASH_CENTS
    assert ensure_player_starting_cash(world) == PLAYER_STARTING_CASH_CENTS


def test_ensure_player_starting_cash_refunds_excess_to_target() -> None:
    """Force-reconcile: if bootstrap accidentally over-funds the player, the
    helper refunds the surplus to the system reserve."""
    world = bootstrap_genesis(seed=9)
    player = PartyId("player")
    acct = party_cash_account(player)
    extra = 5_000_000
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=extra,
    )
    assert int(world.ledger.balance(acct)) == PLAYER_STARTING_CASH_CENTS + extra
    bal = ensure_player_starting_cash(world)
    assert bal == PLAYER_STARTING_CASH_CENTS

"""Human player starting balances (solo / dev bootstrap)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from realm.world import World

# $100,000.00 — default cash for PartyId("player") on new world / dev reset.
PLAYER_STARTING_CASH_CENTS: Final[int] = 10_000_000

# Genesis algorithmic settlers still spawn lean; only the human starts at 100K.
GENESIS_SETTLER_STARTING_CASH_CENTS: Final[int] = 1_000_000

# Scenarios where the human should hold PLAYER_STARTING_CASH_CENTS at tick 0.
_PLAYER_STARTING_SCENARIOS: Final[frozenset[str]] = frozenset({"genesis", "frontier", "cartel"})


def ensure_player_starting_cash(world: "World") -> int:
    """Guarantee human cash ≥ PLAYER_STARTING_CASH_CENTS for standard solo scenarios.

    Stale solo Python processes can still run old bootstrap bytecode that seeded
    $10k (1_000_000 cents). ``POST /dev/reset`` calls this after every rebuild so
    the ledger matches the current constant without requiring a manual process kill.
    """
    from realm.core.ids import PartyId
    from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account

    if str(world.scenario_id) not in _PLAYER_STARTING_SCENARIOS:
        return int(world.ledger.balance(party_cash_account(PartyId("player"))))

    player = PartyId("player")
    acct = party_cash_account(player)
    world.ledger.ensure_account(acct)
    bal = int(world.ledger.balance(acct))
    if bal >= PLAYER_STARTING_CASH_CENTS:
        return bal
    need = PLAYER_STARTING_CASH_CENTS - bal
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=need,
    )
    if isinstance(tr, MoneyErr):
        raise ValueError(tr.reason)
    return int(world.ledger.balance(acct))

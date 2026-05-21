"""Human player starting balances (solo / dev bootstrap)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from realm.world import World

# $100,000.00 — default cash for PartyId("player") on new world / dev reset.
PLAYER_STARTING_CASH_CENTS: Final[int] = 10_000_000

# Genesis algorithmic settlers still spawn lean; only the human starts at 100K.
GENESIS_SETTLER_STARTING_CASH_CENTS: Final[int] = 1_000_000

# Inventory demurrage — excess stock above free tier costs cash per game-day.
FREE_STORAGE_UNITS_PER_PARTY: Final[int] = 100
HOLDING_COST_CENTS_PER_UNIT_DAY: Final[int] = 1
HOLDING_COST_INTERVAL_TICKS: Final[int] = 1440

# Scenarios where the human should hold PLAYER_STARTING_CASH_CENTS at tick 0.
_PLAYER_STARTING_SCENARIOS: Final[frozenset[str]] = frozenset({"genesis", "frontier", "cartel"})

_log = logging.getLogger("uvicorn.error")


def ensure_player_starting_cash(world: "World") -> int:
    """Force human cash to **exactly** PLAYER_STARTING_CASH_CENTS at tick 0.

    Stale solo Python workers can still run old bootstrap bytecode that seeded
    $10k (1_000_000 cents). ``POST /dev/reset`` calls this after every rebuild so
    the ledger matches the current constant without requiring a manual process kill.

    Force-reconciles in **both** directions: tops up if low, refunds to the system
    reserve if high. This makes new-world cash deterministic regardless of which
    code was loaded into the running Python process.
    """
    from realm.core.ids import PartyId
    from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account

    player = PartyId("player")
    acct = party_cash_account(player)
    world.ledger.ensure_account(acct)
    bal_before = int(world.ledger.balance(acct))

    if str(world.scenario_id) not in _PLAYER_STARTING_SCENARIOS:
        _log.info(
            "ensure_player_starting_cash: scenario=%r not gated; balance=%d (skipped)",
            world.scenario_id,
            bal_before,
        )
        return bal_before

    target = PLAYER_STARTING_CASH_CENTS
    if bal_before == target:
        _log.info(
            "ensure_player_starting_cash: scenario=%r already at target=%d",
            world.scenario_id,
            target,
        )
        return bal_before

    if bal_before < target:
        delta = target - bal_before
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=delta,
        )
        action = f"top-up +{delta}"
    else:
        delta = bal_before - target
        tr = world.ledger.transfer(
            debit=acct,
            credit=system_reserve_account(),
            amount_cents=delta,
        )
        action = f"refund -{delta}"
    if isinstance(tr, MoneyErr):
        raise ValueError(tr.reason)
    bal_after = int(world.ledger.balance(acct))
    _log.info(
        "ensure_player_starting_cash: scenario=%r %s before=%d after=%d target=%d",
        world.scenario_id,
        action,
        bal_before,
        bal_after,
        target,
    )
    return bal_after

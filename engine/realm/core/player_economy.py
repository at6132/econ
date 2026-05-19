"""Human player starting balances (solo / dev bootstrap)."""

from __future__ import annotations

from typing import Final

# $100,000.00 — default cash for PartyId("player") on new world / dev reset.
PLAYER_STARTING_CASH_CENTS: Final[int] = 10_000_000

# Genesis algorithmic settlers still spawn lean; only the human starts at 100K.
GENESIS_SETTLER_STARTING_CASH_CENTS: Final[int] = 1_000_000

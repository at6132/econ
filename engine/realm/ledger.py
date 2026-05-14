"""Backwards-compatibility shim — ledger moved to ``realm.core.ledger``.

Existing code that does ``from realm.ledger import X`` continues to work.
New code should use ``from realm.core.ledger import X``.
"""

from __future__ import annotations

from realm.core.ledger import *  # noqa: F401,F403
from realm.core.ledger import (  # noqa: F401  (explicit re-export for type checkers)
    Ledger,
    MoneyErr,
    MoneyOk,
    MoneyResult,
    contract_escrow_account,
    market_escrow_account,
    party_cash_account,
    system_reserve_account,
)

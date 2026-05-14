"""Realm core primitives — IDs, ledger, inventory, RNG, time scale.

This package has NO dependencies on other ``realm.*`` modules. Anything in
``core/`` is foundational and may be imported by every other domain.
"""

from realm.core.ids import (  # noqa: F401
    AccountId,
    MaterialId,
    PartyId,
    PlotId,
)
from realm.core.inventory import (  # noqa: F401
    Inventory,
    MatterErr,
    MatterOk,
    MatterResult,
)
from realm.core.ledger import (  # noqa: F401
    Ledger,
    MoneyErr,
    MoneyOk,
    MoneyResult,
    contract_escrow_account,
    market_escrow_account,
    party_cash_account,
    system_reserve_account,
)
from realm.core.rng import make_rng  # noqa: F401
from realm.core.time_scale import TICKS_PER_GAME_DAY  # noqa: F401

"""Backwards-compatibility shim — inventory moved to ``realm.core.inventory``.

Existing code that does ``from realm.inventory import X`` continues to work.
New code should use ``from realm.core.inventory import X``.
"""

from __future__ import annotations

from realm.core.inventory import *  # noqa: F401,F403
from realm.core.inventory import (  # noqa: F401  (explicit re-export for type checkers)
    Inventory,
    MatterErr,
    MatterOk,
    MatterResult,
)

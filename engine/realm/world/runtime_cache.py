"""Per-world ephemeral caches — never persisted (not in ``scenario_state``).

Tick-scoped lookups (settler scans, owner plot counts, grid bounds) live here so
``dump_world`` / SQLite saves stay JSON-safe.
"""

from __future__ import annotations

from typing import Any

# ``World`` is a dataclass and not weakref-hashable; one live world per solo process.
_BY_WORLD_ID: dict[int, dict[str, Any]] = {}


def bucket(world: object) -> dict[str, Any]:
    wid = id(world)
    store = _BY_WORLD_ID.get(wid)
    if store is None:
        store = {}
        _BY_WORLD_ID[wid] = store
    return store

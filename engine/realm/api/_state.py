"""Shared dev singletons for the realm.api package.

The HTTP API's dev mode keeps a single in-memory ``World`` object that is
the source of truth for every request. ``POST /dev/reset`` reassigns this
attribute; readers in router modules access it via ``_state.WORLD`` so the
reassignment is reflected everywhere immediately.

Real production-mode persistence happens through ``realm.api.persistence``
(SQLite snapshots).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from realm.world import bootstrap_by_scenario

if TYPE_CHECKING:  # pragma: no cover
    from realm.world import World

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SAVE_PATH = _REPO_ROOT / "saves" / "realm_dev.sqlite"

# The current dev-mode World. Reassigned by ``POST /dev/reset``.
WORLD: "World" = bootstrap_by_scenario(seed=42, scenario="genesis")


def _save_path(path: str | None) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = _REPO_ROOT / p
    else:
        p = _DEFAULT_SAVE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

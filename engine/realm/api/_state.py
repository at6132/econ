"""Shared dev singletons for the realm.api package.

The HTTP API's dev mode keeps a single in-memory ``World`` object that is
the source of truth for every request. ``POST /dev/reset`` reassigns this
attribute; readers in router modules access it via ``_state.WORLD``.

The singleton is **lazy**: importing ``realm.api.app`` must not bootstrap a full
solo Genesis map (~30k plots). First access to ``WORLD`` constructs it.

Real production-mode persistence happens through ``realm.api.persistence``
(SQLite snapshots).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from realm.world import World

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SAVE_PATH = _REPO_ROOT / "saves" / "realm_dev.sqlite"

_world_lazy_singleton: World | None = None

_log = logging.getLogger("uvicorn.error")


def __getattr__(name: str):
    """Lazy-load default genesis world on first ``_state.WORLD`` access."""
    global _world_lazy_singleton
    if name == "WORLD":
        if _world_lazy_singleton is None:
            from realm.world import bootstrap_by_scenario

            _seed = 42
            _scenario = "genesis"
            _log.info(
                "Realm: lazy WORLD bootstrap starting (seed=%s scenario=%r). "
                "Genesis has no fixed ETA; this log line marks wall-clock start.",
                _seed,
                _scenario,
            )
            t0 = time.perf_counter()
            _world_lazy_singleton = bootstrap_by_scenario(seed=_seed, scenario=_scenario)
            elapsed = time.perf_counter() - t0
            _log.info(
                "Realm: lazy WORLD bootstrap finished in %.1fs (world.tick=%s).",
                elapsed,
                _world_lazy_singleton.tick,
            )
        return _world_lazy_singleton
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _save_path(path: str | None) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = _REPO_ROOT / p
    else:
        p = _DEFAULT_SAVE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

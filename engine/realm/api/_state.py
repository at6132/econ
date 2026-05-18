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
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from realm.world import World

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAVES_DIR = _REPO_ROOT / "saves"
_DEFAULT_SAVE_PATH = _SAVES_DIR / "realm_dev.sqlite"
_AUTOSAVE_PATH = _SAVES_DIR / "autosave.sqlite"

_world_lazy_singleton: World | None = None
_world_bootstrap_lock = threading.Lock()

# Re-entrant lock guarding ALL world mutation. Acquired by:
#   * the solo sim loop around each ``advance_tick`` (one ticks per call)
#   * action request handlers (claim, trade, build, …) for the duration of
#     the call so they can't race the loop.
# RLock so a request that itself calls ``advance_tick`` (e.g. ``/dev/reset``)
# doesn't deadlock. Game logic is single-threaded under this lock.
WORLD_LOCK = threading.RLock()

# Tracked for ``GET /persistence/status`` so the UI can show "saved Ns ago".
_last_save_at: int = 0
_last_save_path: str = ""
_last_save_kind: str = ""  # "manual" | "autosave"

_log = logging.getLogger("uvicorn.error")


def is_world_initialized() -> bool:
    """``True`` once a ``WORLD`` exists — used by autosave to avoid triggering a
    multi-minute genesis build on a fresh process.

    Two paths populate the world:
      * lazy bootstrap on first ``__getattr__`` lookup → ``_world_lazy_singleton``.
      * ``/dev/reset`` / ``/persistence/load`` assign ``_state.WORLD = X`` directly,
        which lands in this module's ``vars()`` but bypasses ``_world_lazy_singleton``.

    Check both without ever calling ``getattr`` (which would trigger the lazy path).
    """
    return _world_lazy_singleton is not None or "WORLD" in globals()


def record_save(path: str, kind: str) -> None:
    """Stamp last-save metadata for ``GET /persistence/status``."""
    global _last_save_at, _last_save_path, _last_save_kind
    _last_save_at = int(time.time())
    _last_save_path = path
    _last_save_kind = kind


def last_save_info() -> dict[str, object]:
    return {
        "last_save_at": _last_save_at,
        "last_save_path": _last_save_path,
        "last_save_kind": _last_save_kind,
    }


def safe_save_path(slot_or_path: str | None) -> Path:
    """Resolve a user-supplied save slot/path to ``<repo>/saves/<name>.sqlite``.

    Refuses anything that resolves outside the saves directory. Accepts:
      * ``None`` / empty → default ``realm_dev.sqlite``
      * a bare slot name (``"current"`` → ``saves/current.sqlite``)
      * a relative path under ``saves/`` (``"saves/foo.sqlite"``)

    Raises ``ValueError`` if the path escapes the saves directory.
    """
    _SAVES_DIR.mkdir(parents=True, exist_ok=True)
    if not slot_or_path:
        return _DEFAULT_SAVE_PATH
    raw = str(slot_or_path).strip()
    if not raw:
        return _DEFAULT_SAVE_PATH
    # Bare slot name like "current" or "frontier_1" → saves/<name>.sqlite
    if "/" not in raw and "\\" not in raw and not raw.lower().endswith(".sqlite"):
        return _SAVES_DIR / f"{raw}.sqlite"
    p = Path(raw)
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    else:
        p = p.resolve()
    try:
        p.relative_to(_SAVES_DIR.resolve())
    except ValueError as e:
        raise ValueError(
            f"save path must live under {_SAVES_DIR.as_posix()!r} (got {p.as_posix()!r})"
        ) from e
    if p.suffix.lower() != ".sqlite":
        raise ValueError(f"save path must end in .sqlite (got {p.name!r})")
    return p


def __getattr__(name: str):
    """Lazy-load default genesis world on first ``_state.WORLD`` access."""
    global _world_lazy_singleton
    if name == "WORLD":
        if _world_lazy_singleton is None:
            with _world_bootstrap_lock:
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
    """Backwards-compatible wrapper around ``safe_save_path`` (jailed to ``saves/``)."""
    return safe_save_path(path)

"""HTTP API layer (FastAPI). NO game logic lives here.

Submodules:
  * ``realm.api.app``           — FastAPI app, middleware, dev singleton, helpers
  * ``realm.api.serialization`` — JSON dump/load of world state (formerly ``realm.state_io``)
  * ``realm.api.persistence``   — SQLite snapshot save/load (formerly ``realm.persistence``)

The routes are still defined directly on the ``app`` object inside
``realm.api.app``. They will be split into ``routes_*.py`` files using
``APIRouter`` in a follow-up commit.

Tests do ``from realm.api import app``; that import path keeps working.
The dev singleton ``_world`` is exposed via package-level ``__getattr__``
so that ``realm.api._world`` always returns the *current* value (it gets
reassigned by ``POST /dev/reset``).
"""

from __future__ import annotations

from typing import Any

from realm.api.app import app  # noqa: F401


def __getattr__(name: str) -> Any:
    """Delegate attribute lookups to the ``realm.api.app`` submodule.

    Tests poke ``realm.api._world`` and ``realm.api._save_path``; this
    keeps those legacy access paths working after the package split.

    NB: we use ``importlib`` instead of ``from realm.api import app``
    because the latter resolves to the FastAPI ``app`` object that we
    re-exported above, not to the ``app`` submodule.
    """
    import importlib

    _app_module = importlib.import_module("realm.api.app")
    if hasattr(_app_module, name):
        return getattr(_app_module, name)
    raise AttributeError(f"module 'realm.api' has no attribute {name!r}")

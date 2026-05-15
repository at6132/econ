"""FastAPI app: middleware, router registration, dev singletons.

NO game logic. NO routes defined directly here -- every route lives in a
``routes_*.py`` file under this package. The dev-mode shared world and
helpers live in ``_state``.

Tests import ``app`` from ``realm.api`` (or from ``realm.api.app``):

    from realm.api import app           # via __init__.py re-export
    from realm.api.app import app       # this module

Both paths return the same ``FastAPI`` instance.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from realm.api import (
    _state,  # noqa: F401  (kept importable for tests doing ``api._state.WORLD``)
    routes_actions,
    routes_analytics,
    routes_contracts,
    routes_dev,
    routes_economy_depth,
    routes_routes,
    routes_world,
)

# Backwards-compat alias: legacy code (and tests) read ``realm.api.app._world``.
# We expose it as a module-attribute *getter* via ``__getattr__`` so reassignments
# of ``_state.WORLD`` (by ``POST /dev/reset``) are seen by every reader.


def __getattr__(name: str):
    if name == "_world":
        return _state.WORLD
    if name == "_save_path":
        return _state._save_path
    raise AttributeError(f"module 'realm.api.app' has no attribute {name!r}")


app = FastAPI(title="Realm Engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_world.router)
app.include_router(routes_routes.router)
app.include_router(routes_actions.router)
app.include_router(routes_contracts.router)
app.include_router(routes_analytics.router)
app.include_router(routes_economy_depth.router)
app.include_router(routes_dev.router)

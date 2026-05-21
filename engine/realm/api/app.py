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

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

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
    routes_sim,
    routes_ws,
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


_log = logging.getLogger("uvicorn.error")
# Uvicorn configures ``uvicorn.error`` at the CLI log level; the root logger often
# stays WARNING, so ``logging.getLogger("realm.api")`` INFO lines were invisible.


def _autosave_seconds() -> int:
    """Server-side autosave cadence (seconds). 0 disables. Env: ``REALM_AUTOSAVE_SECONDS``."""
    raw = os.environ.get("REALM_AUTOSAVE_SECONDS", "60")
    try:
        return max(0, int(raw))
    except ValueError:
        return 60


async def _autosave_loop(interval: int) -> None:
    """Background autosave — skips while the lazy WORLD is uninitialized so we
    don't trigger a multi-minute genesis bootstrap from a background task."""
    from realm.api import _state
    from realm.api.persistence import save_snapshot

    _log.info("Realm: autosave loop started (every %ds, per-world files).", interval)
    while True:
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        if not _state.is_world_initialized():
            continue
        path = _state.autosave_path_for_world(_state.WORLD)
        try:
            t0 = time.perf_counter()
            await asyncio.to_thread(save_snapshot, str(path), _state.WORLD)
            _state.record_save(str(path), "autosave")
            _log.info(
                "Realm: autosave wrote %s in %.2fs (tick=%s).",
                path.name,
                time.perf_counter() - t0,
                _state.WORLD.tick,
            )
        except Exception as e:  # autosave must never crash the server
            _log.warning("Realm: autosave failed: %s", e)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    from realm.api import _state

    # Solo Godot uses socket_server thread autosave (asyncio does not run between recv).
    interval = 0 if os.environ.get("REALM_SOLO_MODE") else _autosave_seconds()
    _state.AUTOSAVE_SECONDS = _autosave_seconds()  # type: ignore[attr-defined]
    _log.info(
        "Realm: HTTP stack ready (this step is fast). Dev WORLD is still empty — "
        "it is built lazily on the first request that reads _state.WORLD (default "
        "scenario genesis can take many minutes; there is no ETA until that work starts)."
    )
    _log.info(
        "Realm: For a smaller first boot, after the server is up run once: "
        "curl -X POST \"http://127.0.0.1:8000/dev/reset?scenario=frontier&seed=1\""
    )
    task: asyncio.Task[None] | None = None
    if interval > 0:
        task = asyncio.create_task(_autosave_loop(interval))
    else:
        _log.info("Realm: autosave disabled (REALM_AUTOSAVE_SECONDS=0).")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        _log.info("Realm: API shutdown (lifespan end).")


app = FastAPI(title="Realm Engine", version="0.1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_ws.router)
app.include_router(routes_world.router)
app.include_router(routes_routes.router)
app.include_router(routes_actions.router)
app.include_router(routes_contracts.router)
app.include_router(routes_analytics.router)
app.include_router(routes_economy_depth.router)
app.include_router(routes_dev.router)
app.include_router(routes_sim.router)

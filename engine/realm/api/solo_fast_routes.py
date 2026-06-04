"""Lightweight handlers for the Godot main menu (no full FastAPI import).

The monolithic ``realm.api.app`` pulls in every router and action module (~1s+
on a warm machine, much worse on cold Windows with AV). Solo socket dispatch
uses these for Continue / version checks so port 9000 can accept clients
immediately. Heavy routes (``/dev/reset``, ``/world/map``, …) still go through
``TestClient`` and trigger a one-time full stack load on first use.
"""

from __future__ import annotations

from typing import Any

from realm.api import _state
from realm.api.persistence import read_meta


def get_health() -> dict[str, str]:
    return {"status": "ok"}


def get_version() -> dict[str, Any]:
    from realm.core.build_info import version_payload

    return version_payload()


def get_persistence_list() -> dict[str, Any]:
    """Same shape as ``routes_dev.get_persistence_list`` without importing it."""
    _state._SAVES_DIR.mkdir(parents=True, exist_ok=True)
    slots: list[dict[str, object]] = []
    for p in sorted(_state._SAVES_DIR.glob("*.sqlite"), key=lambda x: x.stat().st_mtime, reverse=True):
        rel = p.relative_to(_state._REPO_ROOT).as_posix()
        meta = read_meta(str(p))
        slots.append(
            {
                "path": rel,
                "name": p.stem,
                "mtime": int(p.stat().st_mtime),
                "tick": int(meta.get("tick", 0) or 0),
                "scenario_id": str(meta.get("scenario_id", "")),
                "seed": int(meta.get("seed", 0) or 0),
                "saved_at": int(meta.get("saved_at", 0) or 0),
                "size_bytes": int(p.stat().st_size),
                "world_id": str(meta.get("world_id", "") or ""),
                "world_name": str(meta.get("world_name", "") or ""),
            }
        )
    return {"ok": True, "slots": slots}


def get_persistence_status() -> dict[str, Any]:
    info = _state.last_save_info()
    info["world_initialized"] = _state.is_world_initialized()
    info["autosave_seconds"] = int(getattr(_state, "AUTOSAVE_SECONDS", 0) or 0)
    w = _state.WORLD if _state.is_world_initialized() else None
    info["world_id"] = str(getattr(w, "world_id", "") or "") if w is not None else ""
    info["primary_slot"] = _state.primary_slot_for_world(w)
    ap = _state.autosave_path_for_world(w)
    info["autosave_path"] = ap.relative_to(_state._REPO_ROOT).as_posix()
    info["ok"] = True
    return info


_FAST_GET: dict[str, Any] = {
    "/health": get_health,
    "/version": get_version,
    "/persistence/list": get_persistence_list,
    "/persistence/status": get_persistence_status,
}


def try_fast_dispatch(method: str, path_only: str) -> dict[str, Any] | None:
    if method.upper() != "GET":
        return None
    handler = _FAST_GET.get(path_only)
    if handler is None:
        return None
    return handler()

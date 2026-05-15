"""Phase 10B — shipping route registry & voyage history (read-mostly API)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from realm.actions.shipping_actions import register_route as register_route_action
from realm.api import _state
from realm.core.ids import PartyId, PlotId
from realm.infrastructure.route_operators import (
    find_cheapest_operator,
    list_route_operators,
    remove_operator_from_route,
)

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("")
def list_all_routes() -> dict[str, Any]:
    w = _state.WORLD
    raw = w.scenario_state.get("route_operators") or {}
    if not isinstance(raw, dict):
        return {"routes": {}}
    out: dict[str, list[dict[str, Any]]] = {}
    for key, entries in raw.items():
        out[str(key)] = list_route_operators(w, str(key))
    return {"routes": out}


@router.get("/history")
def voyage_history() -> dict[str, Any]:
    w = _state.WORLD
    return {"voyage_history": dict(w.voyage_history)}


@router.get("/uncharted")
def uncharted_lanes() -> dict[str, Any]:
    """Routes with completed voyages but no registered operator."""
    w = _state.WORLD
    keys: list[str] = []
    for rk, n in (w.voyage_history or {}).items():
        if int(n) <= 0:
            continue
        if find_cheapest_operator(w, str(rk)) is None:
            keys.append(str(rk))
    keys.sort()
    return {"route_keys": keys}


@router.post("/register")
def register_route_endpoint(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    party = PartyId(str(payload.get("party", "player")))
    plot_id = PlotId(str(payload["plot_id"]))
    from_region = str(payload["from_region"])
    to_region = str(payload["to_region"])
    fee = int(payload.get("fee_per_tile_cents", 3))
    res = register_route_action(
        _state.WORLD,
        party,
        plot_id,
        from_region,
        to_region,
        fee,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason", res))
    return res


@router.delete("/{route_key:path}")
def delete_route_registration(
    route_key: str,
    party: str = "player",
) -> dict[str, Any]:
    res = remove_operator_from_route(_state.WORLD, PartyId(party), route_key)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason", res))
    return res

"""Sim control endpoints — pause / resume / set speed / status.

These are **host-level** controls, not game-state mutation. The actual
clock state lives in ``realm.world.sim_clock``; this module is the wire
surface. Tests can manipulate the clock directly without going through
HTTP.

In solo mode, ``socket_server`` registers a tick-frame push callback so a
status change is broadcast immediately (the loop reads the new state on
its next slice — within ~50 ms).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException

from realm.api import sim_loop
from realm.world.sim_clock import get_sim_clock

router = APIRouter()


def _broadcast_status(extra: dict[str, Any] | None = None) -> None:
    """Push the new clock state to every subscriber so UI can update without polling."""
    clk = get_sim_clock()
    payload: dict[str, Any] = {"kind": "sim_status", **clk.status_dict()}
    if extra:
        payload.update(extra)
    sim_loop._push_to_all(payload)


@router.get("/sim/status")
def get_sim_status() -> dict[str, Any]:
    """Host clock + speed presets + frames-emitted counter. Safe to call any time."""
    return get_sim_clock().status_dict()


@router.post("/sim/control")
def post_sim_control(body: Annotated[dict, Body()] = None) -> dict[str, Any]:  # type: ignore[assignment]
    """Set pause and/or speed in one round-trip.

    Body fields (all optional):
      * ``paused`` (bool) — set the pause flag.
      * ``speed`` (number) — snap to the nearest preset; ``0`` pauses.

    Returns the **new** status. Idempotent.
    """
    body = body or {}
    clk = get_sim_clock()

    if "speed" in body and body["speed"] is not None:
        try:
            clk.set_speed(float(body["speed"]))
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"speed must be a number: {e}") from e

    if "paused" in body and body["paused"] is not None:
        if not isinstance(body["paused"], bool):
            raise HTTPException(status_code=400, detail="paused must be a boolean")
        clk.set_paused(bool(body["paused"]))

    _broadcast_status()
    return clk.status_dict()

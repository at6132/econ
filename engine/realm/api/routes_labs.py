"""Realm Labs API — preset catalog and lab session start."""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from realm.api import _state
from realm.core.ids import PartyId, new_world_id, normalize_world_id
from realm.core.ledger import party_cash_account
from realm.labs import (
    LAB_CATEGORIES,
    bootstrap_lab_preset,
    catalog_stats,
    get_lab_preset,
    list_lab_presets,
)
from realm.labs.preset_schema import LabOverrides
from realm.world import bootstrap_by_scenario

router = APIRouter(prefix="/labs", tags=["labs"])
_log = logging.getLogger("uvicorn.error")


class LabsStartBody(BaseModel):
    preset_id: str
    seed: int | None = None
    overrides: dict[str, Any] | None = None
    world_name: str = ""


def _lab_overrides(raw: dict[str, Any] | None) -> LabOverrides | None:
    if not raw:
        return None
    out: LabOverrides = {}
    for key in ("seed", "map_scale_pct", "cash_scale_pct", "settler_count", "sim_speed"):
        if key in raw and raw[key] is not None:
            out[key] = int(raw[key])  # type: ignore[literal-required]
    return out if out else None


@router.get("/presets")
def labs_list_presets(
    category: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    featured_only: Annotated[bool, Query()] = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 48,
) -> dict:
    page, total = list_lab_presets(
        category=category,
        tag=tag,
        q=q,
        featured_only=featured_only,
        offset=offset,
        limit=limit,
    )
    return {
        "ok": True,
        "presets": [p.public_dict() for p in page],
        "total": total,
        "offset": offset,
        "limit": limit,
        "categories": list(LAB_CATEGORIES),
        "stats": catalog_stats(),
    }


@router.get("/presets/{preset_id}")
def labs_get_preset(preset_id: str) -> dict:
    try:
        preset = get_lab_preset(preset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "preset": preset.detail_dict()}


@router.post("/start")
def labs_start(body: LabsStartBody) -> dict:
    """Bootstrap a lab preset into the singleton WORLD."""
    from realm.core.player_economy import ensure_player_starting_cash
    from realm.world.sim_clock import get_sim_clock

    _log.info(
        "Realm: POST /labs/start preset=%r seed=%s",
        body.preset_id,
        body.seed,
    )
    clk = get_sim_clock()
    was_paused = clk.paused
    clk.set_paused(True)
    t0 = time.perf_counter()
    try:
        try:
            w = bootstrap_lab_preset(
                preset_id=body.preset_id,
                seed=body.seed,
                overrides=_lab_overrides(body.overrides),
                world_name=body.world_name,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        wid = new_world_id()
        w.world_id = str(wid)
        with _state.WORLD_LOCK:
            _state.assign_world(w)
        player_cash = ensure_player_starting_cash(_state.WORLD)
        ov = body.overrides or {}
        sim_speed_idx = int(ov.get("sim_speed", 2))
        speed_mult = (0.5, 1.0, 2.0)[max(0, min(2, sim_speed_idx))]
        clk.set_speed(speed_mult)
        from realm.api import sim_loop

        sim_loop._push_to_all({"kind": "sim_status", **clk.status_dict()})
        sim_loop._push_to_all(sim_loop.build_tick_frame())
        preset = get_lab_preset(body.preset_id)
        elapsed = time.perf_counter() - t0
        _log.info("Realm: POST /labs/start finished in %.1fs", elapsed)
        return {
            "ok": True,
            "seed": w.seed,
            "world_id": str(wid),
            "scenario_id": w.scenario_id,
            "lab_mode": True,
            "lab_preset_id": preset.id,
            "lab_title": preset.title,
            "lab_category": preset.category,
            "player_cash_cents": player_cash,
            "default_save_slot": _state.lab_save_slot_for_world(w),
        }
    finally:
        if not was_paused:
            clk.set_paused(False)


@router.post("/exit")
def labs_exit(
    scenario: Annotated[str, Query()] = "frontier",
    seed: Annotated[int, Query()] = 42,
) -> dict:
    """Leave lab mode — reset to a campaign scenario (default frontier)."""
    from realm.core.player_economy import ensure_player_starting_cash
    from realm.world.sim_clock import get_sim_clock

    clk = get_sim_clock()
    was_paused = clk.paused
    clk.set_paused(True)
    try:
        try:
            w = bootstrap_by_scenario(seed=seed, scenario=scenario)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        wid = new_world_id()
        w.world_id = str(wid)
        with _state.WORLD_LOCK:
            _state.assign_world(w)
        player_cash = ensure_player_starting_cash(_state.WORLD)
        clk.set_speed(1.0)
        from realm.api import sim_loop

        sim_loop._push_to_all({"kind": "sim_status", **clk.status_dict()})
        sim_loop._push_to_all(sim_loop.build_tick_frame())
        return {
            "ok": True,
            "scenario_id": w.scenario_id,
            "lab_mode": False,
            "player_cash_cents": player_cash,
        }
    finally:
        if not was_paused:
            clk.set_paused(False)

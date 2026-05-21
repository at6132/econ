"""Realm API routes — dev-only endpoints (reset, save/load).

Routes split out of the original monolithic ``realm.api.app`` for
maintainability. The shared dev singleton ``WORLD`` and helpers live in
``realm.api._state``; reassigning it (via ``POST /dev/reset``) updates
the value seen by every router because Python module attributes are
looked up dynamically.

This file is intentionally limited to dispatch: parse arguments, call an
action function, return its result. No game logic in routes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query

from realm.actions import (
    buy_survey_report,
    cancel_survey_report_listing,
    claim_plot,
    harvest_plot_output_stock,
    hire_catalog_public,
    hire_worker_stub,
    list_survey_report,
    register_business,
    start_production_on_plot,
    survey_plot,
    transfer_survey_report,
)
from realm.api import _state
from realm.api.persistence import load_snapshot, read_meta, save_snapshot
from realm.code.lua_sandbox import eval_user_lua_chunk
from realm.code.user_code import code_layer_public_status, validate_user_source
from realm.contracts.social import (
    accept_supply_contract,
    fulfill_supply_contract,
    honor_contract_stub,
    propose_supply_contract,
)
from realm.contracts.stubs import (
    accept_equity_stub,
    accept_forward_contract,
    accept_loan_contract,
    accept_service_sub,
    deliver_forward_contract,
    propose_equity_stub,
    propose_forward_contract,
    propose_loan_contract,
    propose_service_sub,
    repay_loan_contract,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.economy.analytics import purchase_analytics_product
from realm.economy.intel import purchase_market_intel
from realm.economy.markets import (
    cancel_buy_order,
    cancel_sell_order,
    market_buy,
    p2p_trade,
    place_buy_order,
    place_sell_order,
    sell_into_bids,
)
from realm.economy.supply_signals import all_region_activity, trade_flows_overlay
from realm.infrastructure.movement import dispatch_shipment
from realm.infrastructure.roads import all_roads_public, build_road, set_road_toll
from realm.production.buildings import build_on_plot
from realm.production.decay import maintain_building
from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
from realm.production.schematic import validate_linear_recipe_chain
from realm.world import bootstrap_by_scenario, world_compact_dict, world_public_dict
from realm.world.tick import advance_tick

router = APIRouter()

_log = logging.getLogger("uvicorn.error")


@router.post("/dev/reset")
def dev_reset(
    seed: Annotated[int, Query()] = 42,
    scenario: Annotated[str, Query()] = "genesis",
    name: Annotated[str, Query()] = "",
) -> dict:
    """Recreate world (dev). ``scenario`` ∈ frontier, cartel, bootstrapper, speculator, millrace, archive, genesis."""
    _log.info("Realm: POST /dev/reset received (scenario=%r seed=%s) — building world…", scenario, seed)
    from realm.world.sim_clock import get_sim_clock

    clk = get_sim_clock()
    was_paused = clk.paused
    clk.set_paused(True)
    t0 = time.perf_counter()
    try:
        try:
            w = bootstrap_by_scenario(seed=seed, scenario=scenario)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        with _state.WORLD_LOCK:
            _state.assign_world(w)
            if name:
                _state.WORLD.world_name = name
        from realm.core.player_economy import ensure_player_starting_cash

        player_cash_after_ensure = ensure_player_starting_cash(_state.WORLD)
        # Drop stale autosave so Continue cannot resurrect a pre-reset $10k world.
        try:
            if _state._AUTOSAVE_PATH.is_file():
                _state._AUTOSAVE_PATH.unlink()
                _log.info("Realm: removed stale autosave %s after /dev/reset.", _state._AUTOSAVE_PATH.name)
        except OSError as e:
            _log.warning("Realm: could not remove autosave after reset: %s", e)
        from realm.api import sim_loop

        clk.set_speed(1.0)
        sim_loop._push_to_all({"kind": "sim_status", **clk.status_dict()})
        sim_loop._push_to_all(sim_loop.build_tick_frame())
        elapsed = time.perf_counter() - t0
        _log.info(
            "Realm: POST /dev/reset finished in %.1fs (scenario_id=%r tick=%s).",
            elapsed,
            _state.WORLD.scenario_id,
            _state.WORLD.tick,
        )
        from realm.core.ids import PartyId
        from realm.core.ledger import party_cash_account
        from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS

        return {
            "ok": True,
            "seed": seed,
            "scenario_id": w.scenario_id,
            "map_layout": w.scenario_state.get("map_layout"),
            "grid_width": w.scenario_state.get("grid_width"),
            "grid_height": w.scenario_state.get("grid_height"),
            "player_cash_cents": player_cash_after_ensure,
            "player_starting_cash_cents": PLAYER_STARTING_CASH_CENTS,
        }
    finally:
        if not was_paused:
            clk.set_paused(False)


@router.post("/persistence/save")
def post_persistence_save(
    path: Annotated[str | None, Query()] = None,
    slot: Annotated[str | None, Query()] = None,
) -> dict:
    """Persist the current world to ``saves/<slot>.sqlite``.

    Either ``slot`` (bare name, recommended) or ``path`` (relative to repo root,
    must stay under ``saves/``) selects the target. Without either, writes the
    default dev save (``saves/realm_dev.sqlite``).
    """
    try:
        p = _state.safe_save_path(slot or path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    t0 = time.perf_counter()
    save_snapshot(str(p), _state.WORLD)
    _state.record_save(str(p), "manual")
    _log.info(
        "Realm: POST /persistence/save wrote %s in %.2fs (tick=%s).",
        p.name,
        time.perf_counter() - t0,
        _state.WORLD.tick,
    )
    return {"ok": True, "path": p.relative_to(_state._REPO_ROOT).as_posix(), "tick": _state.WORLD.tick}


@router.post("/persistence/load")
def post_persistence_load(
    path: Annotated[str | None, Query()] = None,
    slot: Annotated[str | None, Query()] = None,
) -> dict:
    try:
        p = _state.safe_save_path(slot or path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        w = load_snapshot(str(p))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    _state.assign_world(w)
    from realm.api import sim_loop
    from realm.core.ledger import party_cash_account
    from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS
    from realm.world.sim_clock import get_sim_clock

    clk = get_sim_clock()
    clk.set_paused(False)
    clk.set_speed(1.0)
    sim_loop._push_to_all({"kind": "sim_status", **clk.status_dict()})
    sim_loop._push_to_all(sim_loop.build_tick_frame())
    player_cash = int(w.ledger.balance(party_cash_account(PartyId("player"))))
    _log.info("Realm: POST /persistence/load read %s (tick=%s).", p.name, _state.WORLD.tick)
    return {
        "ok": True,
        "path": p.relative_to(_state._REPO_ROOT).as_posix(),
        "tick": _state.WORLD.tick,
        "player_cash_cents": player_cash,
        "player_starting_cash_cents": PLAYER_STARTING_CASH_CENTS,
    }


@router.get("/persistence/list")
def get_persistence_list() -> dict:
    """List ``saves/*.sqlite`` for the Continue menu, enriched with tick/scenario/seed/saved_at."""
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
                "world_name": str(meta.get("world_name", "") or ""),
            }
        )
    return {"ok": True, "slots": slots}


@router.get("/persistence/status")
def get_persistence_status() -> dict:
    """Return last-save info (manual or autosave) for the in-game HUD."""
    info = _state.last_save_info()
    info["world_initialized"] = _state.is_world_initialized()
    info["autosave_seconds"] = int(getattr(_state, "AUTOSAVE_SECONDS", 0) or 0)
    info["autosave_path"] = _state._AUTOSAVE_PATH.relative_to(_state._REPO_ROOT).as_posix()
    info["ok"] = True
    return info


@router.post("/persistence/clear-all")
def post_persistence_clear_all() -> dict:
    """Delete every ``*.sqlite`` file under ``saves/`` (Continue menu slots)."""
    _state._SAVES_DIR.mkdir(parents=True, exist_ok=True)
    deleted: list[str] = []
    for p in sorted(_state._SAVES_DIR.glob("*.sqlite")):
        rel = p.relative_to(_state._REPO_ROOT).as_posix()
        p.unlink()
        deleted.append(rel)
    _state.clear_save_metadata()
    _log.info("Realm: POST /persistence/clear-all removed %d save(s).", len(deleted))
    return {"ok": True, "deleted": deleted, "count": len(deleted)}

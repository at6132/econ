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
from realm.api.persistence import load_snapshot, save_snapshot
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


@router.post("/dev/reset")
def dev_reset(
    seed: Annotated[int, Query()] = 42,
    scenario: Annotated[str, Query()] = "genesis",
) -> dict:
    """Recreate world (dev). ``scenario`` ∈ frontier, cartel, bootstrapper, speculator, millrace, archive, genesis."""
    # (was: global _state.WORLD; mutation now lives on _state.WORLD)
    try:
        _state.WORLD = bootstrap_by_scenario(seed=seed, scenario=scenario)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "seed": seed, "scenario_id": _state.WORLD.scenario_id}


@router.post("/persistence/save")
def post_persistence_save(path: Annotated[str | None, Query()] = None) -> dict:
    p = _state._save_path(path)
    save_snapshot(str(p), _state.WORLD)
    return {"ok": True, "path": str(p)}


@router.post("/persistence/load")
def post_persistence_load(path: Annotated[str | None, Query()] = None) -> dict:
    # (was: global _state.WORLD; mutation now lives on _state.WORLD)
    p = _state._save_path(path)
    try:
        _state.WORLD = load_snapshot(str(p))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "path": str(p), "tick": _state.WORLD.tick}

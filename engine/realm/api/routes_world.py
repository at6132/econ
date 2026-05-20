"""Realm API routes — world reads, tick advance, llm + code endpoints.

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
from realm.api.routes_ws import broadcast_json
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


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def get_version() -> dict:
    """Engine build identity. The Godot client uses this to detect a stale
    realm_solo.py bound to :9000 from a previous run. Bump REALM_BUILD_ID
    whenever shipping a change that breaks compatibility with older clients."""
    from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS

    return {
        "ok": True,
        "build_id": "2026-05-20-cash-100k-v2",
        "player_starting_cash_cents": PLAYER_STARTING_CASH_CENTS,
        "features": {
            "ensure_player_starting_cash": True,
            "dev_reset_returns_player_cash": True,
        },
    }


@router.get("/code/status")
def get_code_status() -> dict:
    """User-code / Lua platform layer (Phase 4) — capability advertisement until sandbox ships."""
    return code_layer_public_status()


@router.post("/code/validate")
def post_code_validate(body: Annotated[dict, Body()]) -> dict:
    """Static validation for future Lua deploy (size / shape only — does not execute)."""
    src = body.get("source")
    if src is None:
        raise HTTPException(status_code=400, detail="missing source")
    if not isinstance(src, str):
        raise HTTPException(status_code=400, detail="source must be a string")
    return validate_user_source(src)


@router.post("/code/deploy")
def post_code_deploy(body: Annotated[dict, Body()]) -> dict:
    """Store Lua source for a party (validated size only; execution is separate / gated)."""
    party_raw = body.get("party", "player")
    src = body.get("source")
    if not isinstance(party_raw, str):
        raise HTTPException(status_code=400, detail="party must be a string")
    if not isinstance(src, str):
        raise HTTPException(status_code=400, detail="source must be a string")
    vr = validate_user_source(src)
    if not vr.get("ok"):
        raise HTTPException(status_code=400, detail=str(vr.get("reason")))
    pid = PartyId(party_raw)
    _state.WORLD.deployed_lua_sources[str(pid)] = src
    return {"ok": True, "party": str(pid), **vr}


@router.post("/code/eval")
def post_code_eval(body: Annotated[dict, Body()]) -> dict:
    """Run Lua chunk (``REALM_LUA_EVAL=1`` + ``lupa`` only — local dev gate)."""
    src = body.get("source")
    if not isinstance(src, str):
        raise HTTPException(status_code=400, detail="source must be a string")
    tick = int(body.get("tick", _state.WORLD.tick))
    purpose = str(body.get("purpose", "api"))
    return eval_user_lua_chunk(src, tick=tick, purpose=purpose)


@router.get("/world")
def get_world(compact: Annotated[int, Query()] = 0) -> dict:
    """Full ``plots`` grid by default; ``compact=1`` returns player-focused summary (dev / long runs)."""
    if compact:
        return world_compact_dict(_state.WORLD)
    return world_public_dict(_state.WORLD)


@router.get("/world/summary")
def get_world_summary(party: Annotated[str, Query()] = "player") -> dict:
    """Sprint 6 — Phase D.4: lightweight HUD payload (poll every ~30 ticks).

    Excludes the plots grid and feed bodies. Just enough for the top bar:
    cash, net-worth estimate, active production, maintenance warnings,
    unread message/feed counters, contract and open-order counts.
    """
    from realm.world import world_summary_dict

    return world_summary_dict(_state.WORLD, PartyId(str(party)))


@router.get("/world/static")
def get_world_static() -> dict:
    """Read-once tables: recipes, building/hire/chemistry catalogs,
    scenario id, seed, ticks_per_game_day, grid size + map layout,
    party display names. Fetch once at boot and after ``/dev/reset``."""
    from realm.world import world_static_dict

    return world_static_dict(_state.WORLD)


@router.get("/world/player")
def get_world_player(party: Annotated[str, Query()] = "player") -> dict:
    """Per-party realtime view: cash, accounts, full inventory, owned
    plots (with subsurface + recipe_ids), owned reports, price alerts,
    in-transit shipments, forward contracts, bank rates + loans, the
    party's recipe book, active production, placed buildings.

    Pair this with ``/world/summary`` on the realtime tick — together
    they cover what the HUD and player-owned panels need without ever
    touching the full ``/world`` payload."""
    from realm.world import world_player_dict

    return world_player_dict(_state.WORLD, PartyId(str(party)))


@router.get("/world/map")
def get_world_map() -> dict:
    """Lean map-only view (terrain / owner / surveyed / powered /
    density / claim_cost per plot). Call once at world-load and after
    structural actions (claim, survey, buy/sell, build, place, demolish)."""
    from realm.world import world_map_dict

    return world_map_dict(_state.WORLD)


@router.get("/world/feed")
def get_world_feed(since_tick: Annotated[int, Query()] = -1) -> dict:
    """Event log + world feed + npc messages.

    ``since_tick < 0`` returns the legacy tails (last 120/1500/48 rows).
    ``since_tick >= 0`` returns only rows newer than that tick — clients
    track their high-water mark and pull deltas."""
    from realm.world import world_feed_dict

    st: int | None = since_tick if since_tick >= 0 else None
    return world_feed_dict(_state.WORLD, since_tick=st)


@router.get("/hire/catalog")
def get_hire_catalog() -> dict:
    return {"roles": hire_catalog_public()}


@router.post("/tick")
async def post_tick() -> dict:
    advance_tick(_state.WORLD)
    await broadcast_json({"kind": "tick", "tick": _state.WORLD.tick})
    return {"ok": True, "tick": _state.WORLD.tick}


# Solo pacing: one game-week is 7 × 1440 ticks; batch avoids 10k sequential HTTP round-trips in dev.
_TICK_BATCH_MAX = 21_600  # 15 game-days cap (dev / automation guardrail)


@router.post("/tick/batch")
def post_tick_batch(
    count: Annotated[int, Query()] = 1,
    summary: Annotated[int, Query()] = 0,
) -> dict:
    """Advance ``count`` ticks in-process (single request). For long runs, prefer this over ``/tick`` spam."""
    if count < 1:
        raise HTTPException(status_code=400, detail="count must be >= 1")
    if count > _TICK_BATCH_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"count must be <= {_TICK_BATCH_MAX} (use multiple calls for longer runs)",
        )
    t0 = _state.WORLD.tick
    for _ in range(count):
        advance_tick(_state.WORLD)
    out: dict = {"ok": True, "tick": _state.WORLD.tick, "advanced": count, "tick_start": t0}
    if summary:
        out["world_compact"] = world_compact_dict(_state.WORLD)
    return out


@router.get("/llm/status")
def get_llm_status() -> dict:
    from realm.agents.llm_haiku import default_model, make_client, session_cap_micro_usd

    cap = session_cap_micro_usd()
    spend = _state.WORLD.llm_session_cost_micro_usd
    return {
        "client_ready": make_client() is not None,
        "model": default_model(),
        "session_cap_micro_usd": cap,
        "session_spend_micro_usd": spend,
        "session_remaining_micro_usd": max(0, cap - spend) if cap > 0 else None,
        "session_input_tokens": _state.WORLD.llm_session_input_tokens,
        "session_output_tokens": _state.WORLD.llm_session_output_tokens,
        "agents": [
            {
                "party": k,
                "display_name": v.get("display_name", k),
                "last_plan_tick": v.get("last_plan_tick"),
                "memory_preview": str(v.get("memory_summary", ""))[:240],
            }
            for k, v in sorted(_state.WORLD.llm_agents.items())
        ],
    }


@router.post("/llm/step")
def post_llm_step(party: Annotated[str, Query()]) -> dict:
    from realm.agents.tier3 import plan_llm_party_once

    r = plan_llm_party_once(_state.WORLD, PartyId(party))
    if not r.get("ok"):
        if r.get("reason") == "no_anthropic_client":
            raise HTTPException(status_code=503, detail=r["reason"])
        raise HTTPException(status_code=400, detail=str(r.get("reason", "llm step failed")))
    return dict(r)

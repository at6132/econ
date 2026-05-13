"""Thin FastAPI layer — clients propose; engine validates (Law 10)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from realm.actions import (
    claim_plot,
    harvest_plot_output_stock,
    hire_catalog_public,
    hire_worker_stub,
    start_production_on_plot,
    survey_plot,
)
from realm.buildings import build_on_plot
from realm.decay import maintain_building
from realm.ids import MaterialId, PartyId, PlotId
from realm.recipe_workshops import recipe_ids_on_plot_for_owner
from realm.intel import purchase_market_intel
from realm.markets import (
    cancel_buy_order,
    cancel_sell_order,
    market_buy,
    p2p_trade,
    place_buy_order,
    place_sell_order,
    sell_into_bids,
)
from realm.movement import dispatch_shipment
from realm.persistence import load_snapshot, save_snapshot
from realm.social import (
    accept_supply_contract,
    fulfill_supply_contract,
    honor_contract_stub,
    propose_contract_stub,
    propose_supply_contract,
)
from realm.contract_stubs import (
    accept_equity_stub,
    accept_loan_contract,
    accept_service_sub,
    propose_equity_stub,
    propose_loan_contract,
    propose_service_sub,
    repay_loan_contract,
)
from realm.schematic import validate_linear_recipe_chain
from realm.lua_sandbox import eval_user_lua_chunk
from realm.tick import advance_tick
from realm.user_code import code_layer_public_status, validate_user_source
from realm.world import bootstrap_by_scenario, bootstrap_frontier, world_compact_dict, world_public_dict

app = FastAPI(title="Realm Engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single in-memory world for dev; optional SQLite via /persistence/*
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SAVE_PATH = _REPO_ROOT / "saves" / "realm_dev.sqlite"

_world = bootstrap_frontier(seed=42)


def _save_path(path: str | None) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = _REPO_ROOT / p
    else:
        p = _DEFAULT_SAVE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/code/status")
def get_code_status() -> dict:
    """User-code / Lua platform layer (Phase 4) — capability advertisement until sandbox ships."""
    return code_layer_public_status()


@app.post("/code/validate")
def post_code_validate(body: Annotated[dict, Body()]) -> dict:
    """Static validation for future Lua deploy (size / shape only — does not execute)."""
    src = body.get("source")
    if src is None:
        raise HTTPException(status_code=400, detail="missing source")
    if not isinstance(src, str):
        raise HTTPException(status_code=400, detail="source must be a string")
    return validate_user_source(src)


@app.post("/code/deploy")
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
    _world.deployed_lua_sources[str(pid)] = src
    return {"ok": True, "party": str(pid), **vr}


@app.post("/code/eval")
def post_code_eval(body: Annotated[dict, Body()]) -> dict:
    """Run Lua chunk (``REALM_LUA_EVAL=1`` + ``lupa`` only — local dev gate)."""
    src = body.get("source")
    if not isinstance(src, str):
        raise HTTPException(status_code=400, detail="source must be a string")
    tick = int(body.get("tick", _world.tick))
    purpose = str(body.get("purpose", "api"))
    return eval_user_lua_chunk(src, tick=tick, purpose=purpose)


@app.get("/world")
def get_world(compact: Annotated[int, Query()] = 0) -> dict:
    """Full ``plots`` grid by default; ``compact=1`` returns player-focused summary (dev / long runs)."""
    if compact:
        return world_compact_dict(_world)
    return world_public_dict(_world)


@app.get("/hire/catalog")
def get_hire_catalog() -> dict:
    return {"roles": hire_catalog_public()}


@app.post("/tick")
def post_tick() -> dict:
    advance_tick(_world)
    return {"ok": True, "tick": _world.tick}


# Solo pacing: one game-week is 7 × 1440 ticks; batch avoids 10k sequential HTTP round-trips in dev.
_TICK_BATCH_MAX = 21_600  # 15 game-days cap (dev / automation guardrail)


@app.post("/tick/batch")
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
    t0 = _world.tick
    for _ in range(count):
        advance_tick(_world)
    out: dict = {"ok": True, "tick": _world.tick, "advanced": count, "tick_start": t0}
    if summary:
        out["world_compact"] = world_compact_dict(_world)
    return out


@app.get("/llm/status")
def get_llm_status() -> dict:
    from realm.llm_haiku import default_model, make_client, session_cap_micro_usd

    cap = session_cap_micro_usd()
    spend = _world.llm_session_cost_micro_usd
    return {
        "client_ready": make_client() is not None,
        "model": default_model(),
        "session_cap_micro_usd": cap,
        "session_spend_micro_usd": spend,
        "session_remaining_micro_usd": max(0, cap - spend) if cap > 0 else None,
        "session_input_tokens": _world.llm_session_input_tokens,
        "session_output_tokens": _world.llm_session_output_tokens,
        "agents": [
            {
                "party": k,
                "display_name": v.get("display_name", k),
                "last_plan_tick": v.get("last_plan_tick"),
                "memory_preview": str(v.get("memory_summary", ""))[:240],
            }
            for k, v in sorted(_world.llm_agents.items())
        ],
    }


@app.post("/llm/step")
def post_llm_step(party: Annotated[str, Query()]) -> dict:
    from realm.agents_tier3 import plan_llm_party_once

    r = plan_llm_party_once(_world, PartyId(party))
    if not r.get("ok"):
        if r.get("reason") == "no_anthropic_client":
            raise HTTPException(status_code=503, detail=r["reason"])
        raise HTTPException(status_code=400, detail=str(r.get("reason", "llm step failed")))
    return dict(r)


@app.post("/plots/{plot_id}/claim")
def post_claim(plot_id: str, party: Annotated[str, Query()] = "player") -> dict:
    party_id = PartyId(party)
    r = claim_plot(_world, party_id, PlotId(plot_id))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/plots/{plot_id}/produce")
def post_produce(
    plot_id: str,
    recipe_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    r = start_production_on_plot(_world, PartyId(party), PlotId(plot_id), recipe_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return r


@app.post("/plots/{plot_id}/survey")
def post_survey(plot_id: str, party: Annotated[str, Query()] = "player") -> dict:
    pid = PlotId(plot_id)
    r = survey_plot(_world, PartyId(party), pid)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    out: dict = dict(r)
    plot = _world.plots.get(pid)
    if plot is not None:
        out["terrain"] = plot.terrain.value
        out["recipe_ids"] = recipe_ids_on_plot_for_owner(_world, plot)
    return out


@app.post("/plots/{plot_id}/schematic/validate")
def post_schematic_validate(
    plot_id: str,
    party: Annotated[str, Query()] = "player",
    body: dict = Body(...),
) -> dict:
    """Authoritative linear-chain validation (engine recipes + party inventory)."""
    pid = PlotId(plot_id)
    plot = _world.plots.get(pid)
    if plot is None:
        raise HTTPException(status_code=404, detail="unknown plot")
    party_id = PartyId(party)
    if plot.owner != party_id:
        raise HTTPException(status_code=400, detail="party does not own this plot")
    if not plot.surveyed:
        raise HTTPException(status_code=400, detail="plot is not surveyed")
    raw = body.get("recipe_ids")
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise HTTPException(status_code=400, detail="body.recipe_ids must be a list of strings")
    return validate_linear_recipe_chain(_world, party_id, raw, plot=plot)


@app.post("/plots/{plot_id}/build")
def post_build(
    plot_id: str,
    building_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
    build_mode: Annotated[str | None, Query()] = None,
) -> dict:
    r = build_on_plot(_world, PartyId(party), PlotId(plot_id), building_id, build_mode=build_mode)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/hire")
def post_hire(
    employer: Annotated[str, Query()],
    employee: Annotated[str, Query()],
    signing_bonus_cents: Annotated[int, Query()],
    wage_per_tick_cents: Annotated[int, Query()] = 0,
    wage_interval_ticks: Annotated[int, Query()] = 1,
) -> dict:
    r = hire_worker_stub(
        _world,
        PartyId(employer),
        PartyId(employee),
        signing_bonus_cents,
        wage_per_tick_cents=wage_per_tick_cents,
        wage_interval_ticks=wage_interval_ticks,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/plots/{plot_id}/maintain")
def post_maintain_building(
    plot_id: str,
    instance_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    row = next((b for b in _world.plot_buildings if str(b.get("instance_id")) == instance_id), None)
    if row is not None and str(row.get("plot_id")) != plot_id:
        raise HTTPException(status_code=400, detail="building instance is not on that plot")
    r = maintain_building(_world, PartyId(party), instance_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/market/intel")
def post_market_intel(party: Annotated[str, Query()] = "player") -> dict:
    r = purchase_market_intel(_world, PartyId(party))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/dev/reset")
def dev_reset(
    seed: Annotated[int, Query()] = 42,
    scenario: Annotated[str, Query()] = "frontier",
) -> dict:
    """Recreate world (dev). ``scenario`` ∈ frontier, cartel, bootstrapper, speculator, millrace, archive, genesis."""
    global _world
    try:
        _world = bootstrap_by_scenario(seed=seed, scenario=scenario)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "seed": seed, "scenario_id": _world.scenario_id}


@app.post("/ship")
def post_ship(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    from_plot: Annotated[str, Query()],
    to_plot: Annotated[str, Query()],
) -> dict:
    r = dispatch_shipment(
        _world,
        PartyId(party),
        MaterialId(material),
        qty,
        PlotId(from_plot),
        PlotId(to_plot),
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/plot/harvest")
def post_plot_harvest(
    party: Annotated[str, Query()],
    plot_id: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
) -> dict:
    r = harvest_plot_output_stock(_world, PartyId(party), PlotId(plot_id), material, qty)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return {"ok": True}


@app.post("/market/sell")
def post_market_sell(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    price_per_unit_cents: Annotated[int, Query()],
    iceberg_display_qty: Annotated[int | None, Query()] = None,
    min_counterparty_honored: Annotated[int, Query()] = 0,
) -> dict:
    r = place_sell_order(
        _world,
        PartyId(party),
        MaterialId(material),
        qty,
        price_per_unit_cents,
        iceberg_display_qty=iceberg_display_qty,
        min_counterparty_honored=min_counterparty_honored,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/market/cancel")
def post_market_cancel(
    party: Annotated[str, Query()],
    order_id: Annotated[str, Query()],
) -> dict:
    r = cancel_sell_order(_world, PartyId(party), order_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/market/bid")
def post_market_bid(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    max_price_per_unit_cents: Annotated[int, Query()],
    iceberg_display_qty: Annotated[int | None, Query()] = None,
    min_counterparty_honored: Annotated[int, Query()] = 0,
) -> dict:
    r = place_buy_order(
        _world,
        PartyId(party),
        MaterialId(material),
        qty,
        max_price_per_unit_cents,
        iceberg_display_qty=iceberg_display_qty,
        min_counterparty_honored=min_counterparty_honored,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/market/cancel_bid")
def post_market_cancel_bid(
    party: Annotated[str, Query()],
    order_id: Annotated[str, Query()],
) -> dict:
    r = cancel_buy_order(_world, PartyId(party), order_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/market/sell_fill")
def post_market_sell_fill(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    max_qty: Annotated[int, Query()],
    min_buyer_honored: Annotated[int, Query()] = 0,
) -> dict:
    r = sell_into_bids(
        _world, PartyId(party), MaterialId(material), max_qty, min_buyer_honored=min_buyer_honored
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/market/buy")
def post_market_buy(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    max_qty: Annotated[int, Query()],
    min_seller_honored: Annotated[int, Query()] = 0,
) -> dict:
    r = market_buy(
        _world,
        PartyId(party),
        MaterialId(material),
        max_qty,
        min_seller_honored=min_seller_honored,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/trade/p2p")
def post_trade_p2p(
    seller: Annotated[str, Query()],
    buyer: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    total_price_cents: Annotated[int, Query()],
    idempotency_key: Annotated[str | None, Query()] = None,
) -> dict:
    r = p2p_trade(
        _world,
        PartyId(seller),
        PartyId(buyer),
        MaterialId(material),
        qty,
        total_price_cents,
        idempotency_key=idempotency_key,
    )
    if not r["ok"]:
        code = r.get("code", "P2P_ERROR")
        raise HTTPException(status_code=400, detail={"reason": r["reason"], "code": code})
    return dict(r)


@app.post("/contracts/supply/propose")
def post_contract_supply_propose(
    supplier: Annotated[str, Query()],
    buyer: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    total_price_cents: Annotated[int, Query()],
    due_in_ticks: Annotated[int, Query()],
    buyer_deposit_cents: Annotated[int, Query()] = 0,
    liquidated_damages_cents: Annotated[int, Query()] = 0,
) -> dict:
    r = propose_supply_contract(
        _world,
        PartyId(supplier),
        PartyId(buyer),
        MaterialId(material),
        qty,
        total_price_cents,
        due_in_ticks,
        buyer_deposit_cents=buyer_deposit_cents,
        liquidated_damages_cents=liquidated_damages_cents,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/supply/accept")
def post_contract_supply_accept(
    buyer: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_supply_contract(_world, PartyId(buyer), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/supply/fulfill")
def post_contract_supply_fulfill(
    supplier: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = fulfill_supply_contract(_world, PartyId(supplier), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/loan/propose")
def post_contract_loan_propose(
    lender: Annotated[str, Query()],
    borrower: Annotated[str, Query()],
    principal_cents: Annotated[int, Query()],
    repay_cents: Annotated[int, Query()],
    due_in_ticks: Annotated[int, Query()],
) -> dict:
    r = propose_loan_contract(
        _world,
        PartyId(lender),
        PartyId(borrower),
        principal_cents,
        repay_cents,
        due_in_ticks,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/loan/accept")
def post_contract_loan_accept(
    borrower: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_loan_contract(_world, PartyId(borrower), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/loan/repay")
def post_contract_loan_repay(
    borrower: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = repay_loan_contract(_world, PartyId(borrower), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/equity/propose")
def post_contract_equity_propose(
    issuer: Annotated[str, Query()],
    investor: Annotated[str, Query()],
    investment_cents: Annotated[int, Query()],
    dividend_per_tick_cents: Annotated[int, Query()],
    dividend_ticks: Annotated[int, Query()],
) -> dict:
    r = propose_equity_stub(
        _world,
        PartyId(issuer),
        PartyId(investor),
        investment_cents,
        dividend_per_tick_cents,
        dividend_ticks,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/equity/accept")
def post_contract_equity_accept(
    investor: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_equity_stub(_world, PartyId(investor), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/service/propose")
def post_contract_service_propose(
    provider: Annotated[str, Query()],
    subscriber: Annotated[str, Query()],
    fee_cents: Annotated[int, Query()],
    duration_ticks: Annotated[int, Query()],
) -> dict:
    r = propose_service_sub(
        _world,
        PartyId(provider),
        PartyId(subscriber),
        fee_cents,
        duration_ticks,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/service/accept")
def post_contract_service_accept(
    subscriber: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_service_sub(_world, PartyId(subscriber), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/contracts/propose")
def post_contract_propose(
    party_a: Annotated[str, Query()],
    party_b: Annotated[str, Query()],
    kind: Annotated[str, Query()] = "supply",
) -> dict:
    return propose_contract_stub(_world, PartyId(party_a), PartyId(party_b), kind)


@app.post("/contracts/{contract_id}/honor")
def post_contract_honor(contract_id: str) -> dict:
    r = honor_contract_stub(_world, contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/persistence/save")
def post_persistence_save(path: Annotated[str | None, Query()] = None) -> dict:
    p = _save_path(path)
    save_snapshot(str(p), _world)
    return {"ok": True, "path": str(p)}


@app.post("/persistence/load")
def post_persistence_load(path: Annotated[str | None, Query()] = None) -> dict:
    global _world
    p = _save_path(path)
    try:
        _world = load_snapshot(str(p))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "path": str(p), "tick": _world.tick}

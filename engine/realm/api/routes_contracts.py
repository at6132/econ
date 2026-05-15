"""Realm API routes — contract lifecycle (supply / loan / equity / service / forward).

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
from typing import Annotated, Any

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
    propose_enforced_contract,
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
from realm.contracts.equity_stake import accept_equity_stake, propose_equity_stake
from realm.contracts.instruments import (
    accept_insurance,
    accept_land_lease,
    buy_loan,
    list_loan_for_sale,
    propose_insurance,
    propose_land_lease,
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


@router.post("/contracts/supply/propose")
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
        _state.WORLD,
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


@router.post("/contracts/supply/accept")
def post_contract_supply_accept(
    buyer: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_supply_contract(_state.WORLD, PartyId(buyer), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/supply/fulfill")
def post_contract_supply_fulfill(
    supplier: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = fulfill_supply_contract(_state.WORLD, PartyId(supplier), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/loan/propose")
def post_contract_loan_propose(
    lender: Annotated[str, Query()],
    borrower: Annotated[str, Query()],
    principal_cents: Annotated[int, Query()],
    repay_cents: Annotated[int, Query()],
    due_in_ticks: Annotated[int, Query()],
) -> dict:
    r = propose_loan_contract(
        _state.WORLD,
        PartyId(lender),
        PartyId(borrower),
        principal_cents,
        repay_cents,
        due_in_ticks,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/loan/accept")
def post_contract_loan_accept(
    borrower: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_loan_contract(_state.WORLD, PartyId(borrower), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/loan/repay")
def post_contract_loan_repay(
    borrower: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = repay_loan_contract(_state.WORLD, PartyId(borrower), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/equity/propose")
def post_contract_equity_propose(
    issuer: Annotated[str, Query()],
    investor: Annotated[str, Query()],
    investment_cents: Annotated[int, Query()],
    dividend_per_tick_cents: Annotated[int, Query()],
    dividend_ticks: Annotated[int, Query()],
) -> dict:
    r = propose_equity_stub(
        _state.WORLD,
        PartyId(issuer),
        PartyId(investor),
        investment_cents,
        dividend_per_tick_cents,
        dividend_ticks,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/equity/accept")
def post_contract_equity_accept(
    investor: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_equity_stub(_state.WORLD, PartyId(investor), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/equity/stake/propose")
def post_contract_equity_stake_propose(
    issuer: Annotated[str, Query()],
    investor: Annotated[str, Query()],
    business_id: Annotated[str, Query()],
    ownership_pct_bps: Annotated[int, Query()],
    investment_cents: Annotated[int, Query()],
) -> dict:
    r = propose_equity_stake(
        _state.WORLD,
        PartyId(issuer),
        PartyId(investor),
        business_id,
        ownership_pct_bps,
        investment_cents,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/equity/stake/accept")
def post_contract_equity_stake_accept(
    investor: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_equity_stake(_state.WORLD, PartyId(investor), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/service/propose")
def post_contract_service_propose(
    provider: Annotated[str, Query()],
    subscriber: Annotated[str, Query()],
    fee_cents: Annotated[int, Query()],
    duration_ticks: Annotated[int, Query()],
    service_id: Annotated[str, Query()],
    service_params_json: Annotated[str | None, Query()] = None,
) -> dict:
    import json

    params: dict[str, Any] | None = None
    if service_params_json:
        try:
            raw = json.loads(service_params_json)
            params = dict(raw) if isinstance(raw, dict) else None
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="service_params_json must be valid JSON object")
    r = propose_service_sub(
        _state.WORLD,
        PartyId(provider),
        PartyId(subscriber),
        fee_cents,
        duration_ticks,
        service_id,
        params,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/service/accept")
def post_contract_service_accept(
    subscriber: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_service_sub(_state.WORLD, PartyId(subscriber), contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/propose")
def post_contract_propose(body: dict[str, Any] = Body(...)) -> dict:
    party_a = PartyId(str(body.get("party_a", "")))
    party_b = PartyId(str(body.get("party_b", "")))
    kind = str(body.get("kind", ""))
    params = dict(body.get("params") or {})
    r = propose_enforced_contract(_state.WORLD, party_a, party_b, kind, params)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/contracts/{contract_id}/honor")
def post_contract_honor(contract_id: str) -> dict:
    r = honor_contract_stub(_state.WORLD, contract_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/contracts/insurance/propose")
def post_insurance_propose(
    insurer: Annotated[str, Query()],
    insured: Annotated[str, Query()],
    covered_event_kind: Annotated[str, Query()],
    payout_cents: Annotated[int, Query()],
    premium_per_7days_cents: Annotated[int, Query()],
    duration_ticks: Annotated[int, Query()],
    covered_plot_id: Annotated[str | None, Query()] = None,
) -> dict:
    r = propose_insurance(
        _state.WORLD,
        PartyId(insurer),
        PartyId(insured),
        covered_event_kind,
        covered_plot_id,
        payout_cents,
        premium_per_7days_cents,
        duration_ticks,
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/contracts/insurance/accept")
def post_insurance_accept(
    insured: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_insurance(_state.WORLD, PartyId(insured), contract_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/contracts/insurance/mine")
def get_insurance_mine(party: Annotated[str, Query()] = "player") -> dict:
    ps = str(party)
    rows = [
        dict(c)
        for c in _state.WORLD.contracts
        if str(c.get("kind", "")) == "insurance"
        and str(c.get("status", "")) in ("active", "proposed")
        and (str(c.get("insured", "")) == ps or str(c.get("insurer", "")) == ps)
    ]
    return {"ok": True, "policies": rows}


@router.post("/loans/market/list")
def post_loan_market_list(
    seller: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
    ask_cents: Annotated[int, Query()],
) -> dict:
    r = list_loan_for_sale(_state.WORLD, PartyId(seller), contract_id, ask_cents)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/loans/market/{contract_id}/buy")
def post_loan_market_buy(
    contract_id: str,
    buyer: Annotated[str, Query()],
) -> dict:
    r = buy_loan(_state.WORLD, PartyId(buyer), contract_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/loans/market")
def get_loan_market() -> dict:
    lm = _state.WORLD.scenario_state.get("loan_market", [])
    if not isinstance(lm, list):
        return {"ok": True, "listings": []}
    return {"ok": True, "listings": list(lm)}


@router.post("/contracts/lease/propose")
def post_lease_propose(
    lessor: Annotated[str, Query()],
    lessee: Annotated[str, Query()],
    plot_id: Annotated[str, Query()],
    rent_per_7days_cents: Annotated[int, Query()],
    duration_ticks: Annotated[int, Query()],
) -> dict:
    r = propose_land_lease(
        _state.WORLD,
        PartyId(lessor),
        PartyId(lessee),
        PlotId(plot_id),
        rent_per_7days_cents,
        duration_ticks,
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/contracts/lease/accept")
def post_lease_accept(
    lessee: Annotated[str, Query()],
    contract_id: Annotated[str, Query()],
) -> dict:
    r = accept_land_lease(_state.WORLD, PartyId(lessee), contract_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/contracts/lease/mine")
def get_lease_mine(party: Annotated[str, Query()] = "player") -> dict:
    ps = str(party)
    rows = [
        dict(c)
        for c in _state.WORLD.contracts
        if str(c.get("kind", "")) == "land_lease"
        and str(c.get("status", "")) in ("active", "proposed")
        and (str(c.get("lessor", "")) == ps or str(c.get("lessee", "")) == ps)
    ]
    return {"ok": True, "leases": rows}


# ─────────────────── Sprint 4 — Phase A: intelligence market ───────────────────


@router.get("/contracts/forward")
def get_forward_contracts(party: Annotated[str, Query()] = "player") -> dict:
    rows: list[dict] = []
    for c in _state.WORLD.contracts:
        if str(c.get("kind", "")) != "forward_contract":
            continue
        if (
            str(c.get("seller", "")) != party
            and str(c.get("buyer", "")) != party
            and party != "*"
        ):
            continue
        rows.append(dict(c))
    return {"ok": True, "tick": _state.WORLD.tick, "forwards": rows}


@router.post("/contracts/forward/propose")
def post_contract_forward_propose(
    seller: Annotated[str, Query()],
    buyer: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    price_per_unit_cents: Annotated[int, Query()],
    delivery_tick: Annotated[int, Query()],
) -> dict:
    r = propose_forward_contract(
        _state.WORLD,
        PartyId(seller),
        PartyId(buyer),
        MaterialId(material),
        qty,
        price_per_unit_cents,
        delivery_tick,
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/contracts/forward/{contract_id}/accept")
def post_contract_forward_accept(
    contract_id: str,
    buyer: Annotated[str, Query()],
) -> dict:
    r = accept_forward_contract(_state.WORLD, PartyId(buyer), contract_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/contracts/forward/{contract_id}/deliver")
def post_contract_forward_deliver(
    contract_id: str,
    seller: Annotated[str, Query()],
) -> dict:
    r = deliver_forward_contract(_state.WORLD, PartyId(seller), contract_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


# ─────────────────── Sprint 4 — Phase D: price alerts ───────────────────

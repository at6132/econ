"""Realm API routes — analytics, alerts, intel, tenders, markets, bank.

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


@router.post("/market/intel")
def post_market_intel(party: Annotated[str, Query()] = "player") -> dict:
    r = purchase_market_intel(_state.WORLD, PartyId(party))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.get("/tenders")
def get_tenders() -> dict:
    """List every tender (open and historical). UI groups by status."""
    from realm.genesis.settler_cost_basis import settler_output_basis_cents
    from realm.contracts.tenders import list_all_tenders

    player = PartyId("player")
    tenders_out = []
    for t in list_all_tenders(_state.WORLD):
        bids = list(t.get("bids") or [])
        bids_sorted = sorted(
            bids,
            key=lambda b: (int(b.get("price_per_unit_cents", 0)), int(b.get("submitted_at_tick", 0))),
        )
        lowest = bids_sorted[0] if bids_sorted else None
        player_bid = next(
            (b for b in bids if str(b.get("bidder")) == str(player)),
            None,
        )
        player_basis = settler_output_basis_cents(_state.WORLD, player, MaterialId(str(t.get("material"))))
        tenders_out.append(
            {
                "id": str(t.get("id")),
                "posted_by": str(t.get("posted_by")),
                "material": str(t.get("material")),
                "qty_per_cycle": int(t.get("qty_per_cycle", 0)),
                "interval_ticks": int(t.get("interval_ticks", 0)),
                "duration_cycles": int(t.get("duration_cycles", 0)),
                "bid_deadline_tick": int(t.get("bid_deadline_tick", 0)),
                "posted_at_tick": int(t.get("posted_at_tick", 0)),
                "bids": [
                    {
                        "bidder": str(b.get("bidder")),
                        "price_per_unit_cents": int(b.get("price_per_unit_cents", 0)),
                        "submitted_at_tick": int(b.get("submitted_at_tick", 0)),
                    }
                    for b in bids_sorted
                ],
                "lowest_bid_cents": int(lowest["price_per_unit_cents"]) if lowest else None,
                "player_bid_cents": (
                    int(player_bid["price_per_unit_cents"]) if player_bid else None
                ),
                "player_estimated_basis_cents": player_basis,
                "awarded_to": (
                    str(t.get("awarded_to")) if t.get("awarded_to") else None
                ),
                "awarded_price_per_unit_cents": (
                    int(t["awarded_price_per_unit_cents"])
                    if t.get("awarded_price_per_unit_cents") is not None
                    else None
                ),
                "awarded_contract_id": (
                    str(t.get("awarded_contract_id"))
                    if t.get("awarded_contract_id")
                    else None
                ),
                "status": str(t.get("status", "open")),
            }
        )
    return {"ok": True, "tick": _state.WORLD.tick, "tenders": tenders_out}


@router.post("/tenders/bid")
def post_tender_bid(
    party: Annotated[str, Query()],
    tender_id: Annotated[str, Query()],
    price_per_unit_cents: Annotated[int, Query()],
) -> dict:
    from realm.contracts.tenders import submit_tender_bid

    r = submit_tender_bid(_state.WORLD, PartyId(party), tender_id, price_per_unit_cents)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/market/sell")
def post_market_sell(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    price_per_unit_cents: Annotated[int, Query()],
    iceberg_display_qty: Annotated[int | None, Query()] = None,
    min_counterparty_honored: Annotated[int, Query()] = 0,
    quality: Annotated[str, Query()] = "standard",
) -> dict:
    r = place_sell_order(
        _state.WORLD,
        PartyId(party),
        MaterialId(material),
        qty,
        price_per_unit_cents,
        iceberg_display_qty=iceberg_display_qty,
        min_counterparty_honored=min_counterparty_honored,
        quality=quality,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/market/cancel")
def post_market_cancel(
    party: Annotated[str, Query()],
    order_id: Annotated[str, Query()],
) -> dict:
    r = cancel_sell_order(_state.WORLD, PartyId(party), order_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/market/bid")
def post_market_bid(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    max_price_per_unit_cents: Annotated[int, Query()],
    iceberg_display_qty: Annotated[int | None, Query()] = None,
    min_counterparty_honored: Annotated[int, Query()] = 0,
) -> dict:
    r = place_buy_order(
        _state.WORLD,
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


@router.post("/market/cancel_bid")
def post_market_cancel_bid(
    party: Annotated[str, Query()],
    order_id: Annotated[str, Query()],
) -> dict:
    r = cancel_buy_order(_state.WORLD, PartyId(party), order_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/market/sell_fill")
def post_market_sell_fill(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    max_qty: Annotated[int, Query()],
    min_buyer_honored: Annotated[int, Query()] = 0,
) -> dict:
    r = sell_into_bids(
        _state.WORLD, PartyId(party), MaterialId(material), max_qty, min_buyer_honored=min_buyer_honored
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/market/buy")
def post_market_buy(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    max_qty: Annotated[int, Query()],
    min_seller_honored: Annotated[int, Query()] = 0,
    max_price_per_unit_cents: Annotated[int | None, Query()] = None,
) -> dict:
    kwargs: dict = {"min_seller_honored": min_seller_honored}
    if max_price_per_unit_cents is not None:
        kwargs["max_price_per_unit_cents"] = int(max_price_per_unit_cents)
    r = market_buy(
        _state.WORLD,
        PartyId(party),
        MaterialId(material),
        max_qty,
        **kwargs,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.get("/intel/listings")
def get_intel_listings(party: Annotated[str, Query()] = "player") -> dict:
    """Active survey-report listings + the requesting party's owned reports."""
    from realm.world import _intel_listings_public, _player_owned_reports_public

    return {
        "ok": True,
        "tick": _state.WORLD.tick,
        "listings": _intel_listings_public(_state.WORLD),
        "owned_reports": _player_owned_reports_public(_state.WORLD, PartyId(party)),
    }


@router.post("/intel/list")
def post_intel_list(
    party: Annotated[str, Query()],
    report_id: Annotated[str, Query()],
    ask_price_cents: Annotated[int, Query()],
) -> dict:
    r = list_survey_report(_state.WORLD, PartyId(party), report_id, ask_price_cents)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/intel/cancel")
def post_intel_cancel(
    party: Annotated[str, Query()],
    listing_id: Annotated[str, Query()],
) -> dict:
    r = cancel_survey_report_listing(_state.WORLD, PartyId(party), listing_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/intel/buy")
def post_intel_buy(
    party: Annotated[str, Query()],
    listing_id: Annotated[str, Query()],
) -> dict:
    r = buy_survey_report(_state.WORLD, PartyId(party), listing_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/intel/transfer")
def post_intel_transfer(
    from_party: Annotated[str, Query()],
    to_party: Annotated[str, Query()],
    report_id: Annotated[str, Query()],
    price_cents: Annotated[int, Query()] = 0,
) -> dict:
    r = transfer_survey_report(
        _state.WORLD, PartyId(from_party), PartyId(to_party), report_id, price_cents
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


# ─────────────────── Sprint 5 — Phase A: business registry ───────────────────


@router.get("/bank/rates")
def get_bank_rates(party: Annotated[str, Query()] = "player") -> dict:
    from realm.genesis.bank import bank_rates_view

    return {"ok": True, "tick": _state.WORLD.tick, **bank_rates_view(_state.WORLD, PartyId(party))}


@router.get("/bank/loans")
def get_bank_loans(party: Annotated[str, Query()] = "player") -> dict:
    from realm.genesis.bank import active_loans_for_borrower

    return {
        "ok": True,
        "tick": _state.WORLD.tick,
        "party": party,
        "loans": active_loans_for_borrower(_state.WORLD, PartyId(party)),
    }


@router.post("/bank/loan/apply")
def post_bank_loan_apply(body: Annotated[dict, Body()]) -> dict:
    from realm.genesis.bank import apply_bank_loan

    party_raw = body.get("party", "player")
    principal = body.get("principal_cents") or body.get("principal") or 0
    num_cycles = body.get("num_cycles") or 1
    coll_raw = body.get("collateral_plot_id")
    try:
        principal_cents = int(principal)
        cycles = int(num_cycles)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="principal and num_cycles must be integers")
    coll_pid = PlotId(str(coll_raw)) if coll_raw else None
    r = apply_bank_loan(
        _state.WORLD, PartyId(str(party_raw)), principal_cents, cycles, coll_pid
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/bank/loan/{loan_id}/repay")
def post_bank_loan_repay(
    loan_id: str, body: Annotated[dict, Body()]
) -> dict:
    from realm.genesis.bank import repay_bank_loan

    party_raw = body.get("party", "player")
    r = repay_bank_loan(_state.WORLD, PartyId(str(party_raw)), loan_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/analytics/purchase")
def post_analytics_purchase(body: Annotated[dict, Body()]) -> dict:
    party_raw = body.get("party", "player")
    product = body.get("product")
    params = body.get("params") or {}
    if not isinstance(product, str):
        raise HTTPException(status_code=400, detail="missing product")
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="params must be an object")
    r = purchase_analytics_product(
        _state.WORLD, PartyId(str(party_raw)), product, params
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/analytics/history")
def get_analytics_history(party: Annotated[str, Query()] = "player") -> dict:
    rows = [row for row in _state.WORLD.analytics_purchases if str(row.get("party", "")) == party]
    return {"ok": True, "purchases": rows[-48:]}


# ─────────────────── Sprint 4 — Phase C: forward contracts ───────────────────


@router.get("/alerts/price")
def get_price_alerts(party: Annotated[str, Query()] = "player") -> dict:
    alerts = list(_state.WORLD.scenario_state.get("player_price_alerts") or [])
    return {"ok": True, "alerts": alerts}


@router.post("/alerts/price")
def post_price_alert(body: Annotated[dict, Body()]) -> dict:
    from realm.events.price_alerts import add_price_alert

    material = body.get("material")
    condition = body.get("condition")
    threshold = body.get("threshold") or body.get("threshold_cents")
    if not isinstance(material, str) or not material:
        raise HTTPException(status_code=400, detail="material is required")
    if condition not in ("below", "above"):
        raise HTTPException(status_code=400, detail="condition must be 'below' or 'above'")
    if not isinstance(threshold, int) or threshold <= 0:
        raise HTTPException(status_code=400, detail="threshold must be a positive integer (cents)")
    r = add_price_alert(_state.WORLD, material, condition, threshold)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.delete("/alerts/price/{alert_id}")
def delete_price_alert(alert_id: str) -> dict:
    from realm.events.price_alerts import remove_price_alert

    r = remove_price_alert(_state.WORLD, alert_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


# ─────────────────── Sprint 6 — Phase C: supply chain visibility ───────────────────


@router.get("/market/depth")
def get_market_depth() -> dict:
    from realm.agents.market_oracle import get_oracle

    oracle = get_oracle(_state.WORLD)
    mats = set(oracle.ask_depth.keys()) | set(oracle.bid_depth.keys())
    return {
        "ok": True,
        "tick": int(_state.WORLD.tick),
        "depth": {
            mat: {
                "ask_depth": int(oracle.ask_depth.get(mat, 0)),
                "bid_depth": int(oracle.bid_depth.get(mat, 0)),
                "seller_count": int(oracle.ask_seller_count.get(mat, 0)),
                "spread_pct": float(oracle.price_spread_pct.get(mat, 0.0)),
            }
            for mat in sorted(mats)
        },
    }


@router.get("/market/signals")
def get_market_signals() -> dict:
    """Aggregated public signals: per-material region activity + trade-flow overlay."""
    return {
        "ok": True,
        "tick": int(_state.WORLD.tick),
        "region_activity": all_region_activity(_state.WORLD),
        "trade_flows": trade_flows_overlay(_state.WORLD),
    }


@router.get("/market/routes")
def get_market_routes() -> dict:
    """Public route operator registry (Phase C.4 — observable without analytics)."""
    raw = _state.WORLD.scenario_state.get("route_operators") or {}
    out: dict[str, list[dict]] = {}
    if isinstance(raw, dict):
        for k, entries in raw.items():
            if not isinstance(entries, list):
                continue
            rows: list[dict] = []
            for e in entries:
                if not isinstance(e, dict):
                    continue
                rows.append(
                    {
                        "operator_party": str(e.get("operator_party") or ""),
                        "fee_per_tile_cents": int(e.get("fee_per_tile_cents", 0)),
                    }
                )
            out[str(k)] = rows
    return {"ok": True, "tick": int(_state.WORLD.tick), "routes": out}


# ─────────────────── Sprint 6 — Phase A: roads ───────────────────

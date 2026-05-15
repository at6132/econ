"""Realm API routes — player-facing action endpoints (plots, hires, ship, accounts, business).

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
    propose_contract_stub,
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


@router.post("/plots/{plot_id}/claim")
def post_claim(plot_id: str, party: Annotated[str, Query()] = "player") -> dict:
    party_id = PartyId(party)
    r = claim_plot(_state.WORLD, party_id, PlotId(plot_id))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/plots/{plot_id}/produce")
def post_produce(
    plot_id: str,
    recipe_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
    run_count: Annotated[int, Query()] = 1,
) -> dict:
    from realm.production import start_production

    r = start_production(
        _state.WORLD, PartyId(party), PlotId(plot_id), recipe_id, run_count=int(run_count)
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return r


@router.get("/plots/{plot_id}/throughput")
def get_throughput(
    plot_id: str,
    recipe_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    from realm.production import throughput_breakdown

    r = throughput_breakdown(_state.WORLD, PartyId(party), PlotId(plot_id), recipe_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return r


@router.get("/plots/{plot_id}/energy")
def get_plot_energy(plot_id: str) -> dict:
    """Power-coverage report for a single plot (UI: powered/unpowered detail)."""
    from realm.infrastructure.energy import (
        POWER_COVERAGE_RADIUS,
        is_plot_powered,
        nearest_power_source,
        power_sources_for_plot,
    )

    pid = PlotId(plot_id)
    plot = _state.WORLD.plots.get(pid)
    if plot is None:
        raise HTTPException(status_code=404, detail="unknown plot")
    powered = is_plot_powered(_state.WORLD, pid)
    sources = power_sources_for_plot(_state.WORLD, pid) if powered else []
    nearest = None if powered else nearest_power_source(_state.WORLD, pid)
    return {
        "ok": True,
        "plot_id": str(pid),
        "powered": bool(powered),
        "coverage_radius_tiles": POWER_COVERAGE_RADIUS,
        "power_sources": sources,
        "nearest_power_source": nearest,
    }


@router.post("/plots/{plot_id}/survey")
def post_survey(plot_id: str, party: Annotated[str, Query()] = "player") -> dict:
    pid = PlotId(plot_id)
    r = survey_plot(_state.WORLD, PartyId(party), pid)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    out: dict = dict(r)
    plot = _state.WORLD.plots.get(pid)
    if plot is not None:
        out["terrain"] = plot.terrain.value
        out["recipe_ids"] = recipe_ids_on_plot_for_owner(_state.WORLD, plot)
    return out


@router.post("/plots/{plot_id}/schematic/validate")
def post_schematic_validate(
    plot_id: str,
    party: Annotated[str, Query()] = "player",
    body: dict = Body(...),
) -> dict:
    """Authoritative linear-chain validation (engine recipes + party inventory)."""
    pid = PlotId(plot_id)
    plot = _state.WORLD.plots.get(pid)
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
    return validate_linear_recipe_chain(_state.WORLD, party_id, raw, plot=plot)


@router.post("/plots/{plot_id}/build")
def post_build(
    plot_id: str,
    building_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
    build_mode: Annotated[str | None, Query()] = None,
) -> dict:
    r = build_on_plot(_state.WORLD, PartyId(party), PlotId(plot_id), building_id, build_mode=build_mode)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/assay")
def post_assay(
    plot_id: Annotated[str, Query()],
    mineral_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    """Submit a paid mineral assay attempt on a player-owned plot with an ``assay_lab``."""
    from realm.actions.assay_actions import assay_mineral

    r = assay_mineral(_state.WORLD, PartyId(party), PlotId(plot_id), MaterialId(mineral_id))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "assay rejected")))
    return dict(r)


@router.get("/assay/status")
def get_assay_status(party: Annotated[str, Query()] = "player") -> dict:
    """All in-flight assay jobs for ``party``."""
    from realm.actions.assay_actions import party_active_assay_jobs

    return {"jobs": party_active_assay_jobs(_state.WORLD, PartyId(party))}


@router.get("/assay/book")
def get_assay_book(party: Annotated[str, Query()] = "player") -> dict:
    """Full discovered recipe book + per-mineral assay progress for ``party``."""
    from realm.actions.assay_actions import party_recipe_book_summary

    return party_recipe_book_summary(_state.WORLD, PartyId(party))


@router.post("/deep_survey")
def post_deep_survey(
    plot_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    """Start a deep survey on a player-owned plot with a drill_rig and 1 drill_bit."""
    from realm.actions.deep_survey_actions import deep_survey

    r = deep_survey(_state.WORLD, PartyId(party), PlotId(plot_id))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "deep survey rejected")))
    return dict(r)


@router.get("/deep_survey/status")
def get_deep_survey_status(party: Annotated[str, Query()] = "player") -> dict:
    """All in-flight deep survey jobs for ``party``."""
    from realm.actions.deep_survey_actions import party_active_deep_survey_jobs

    return {"jobs": party_active_deep_survey_jobs(_state.WORLD, PartyId(party))}


@router.post("/hire")
def post_hire(
    employer: Annotated[str, Query()],
    employee: Annotated[str, Query()],
    signing_bonus_cents: Annotated[int, Query()],
    wage_per_tick_cents: Annotated[int, Query()] = 0,
    wage_interval_ticks: Annotated[int, Query()] = 1,
) -> dict:
    r = hire_worker_stub(
        _state.WORLD,
        PartyId(employer),
        PartyId(employee),
        signing_bonus_cents,
        wage_per_tick_cents=wage_per_tick_cents,
        wage_interval_ticks=wage_interval_ticks,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/plots/{plot_id}/maintain")
def post_maintain_building(
    plot_id: str,
    instance_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    row = next((b for b in _state.WORLD.plot_buildings if str(b.get("instance_id")) == instance_id), None)
    if row is not None and str(row.get("plot_id")) != plot_id:
        raise HTTPException(status_code=400, detail="building instance is not on that plot")
    r = maintain_building(_state.WORLD, PartyId(party), instance_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/ship")
def post_ship(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    from_plot: Annotated[str, Query()],
    to_plot: Annotated[str, Query()],
) -> dict:
    r = dispatch_shipment(
        _state.WORLD,
        PartyId(party),
        MaterialId(material),
        qty,
        PlotId(from_plot),
        PlotId(to_plot),
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.get("/routes")
def get_routes() -> dict:
    """Shipping market: registered operators per route, per-region partitioning,
    and the player's own revenue/spend totals for today and yesterday."""
    from realm.world.regions import all_region_ids, region_for_plot
    from realm.infrastructure.route_operators import (
        list_route_operators,
        route_revenue_by_party_previous_day,
        route_revenue_by_party_today,
    )

    operators = _state.WORLD.scenario_state.get("route_operators") or {}
    routes_out: list[dict] = []
    for key in sorted(operators.keys()):
        entries = list_route_operators(_state.WORLD, key)
        a, b = key.split(":", 1)
        routes_out.append(
            {
                "key": key,
                "region_a": a,
                "region_b": b,
                "operators": [
                    {
                        "party": str(e.get("operator_party")),
                        "plot_id": str(e.get("operator_plot")),
                        "building": str(e.get("building")),
                        "fee_per_tile_cents": int(e.get("fee_per_tile_cents", 0)),
                        "registered_at_tick": int(e.get("registered_at_tick", 0)),
                    }
                    for e in entries
                ],
            }
        )
    player = PartyId("player")
    # Player-owned plots grouped by region (for the "register a route" form).
    plots_by_region: dict[str, list[str]] = {r: [] for r in all_region_ids()}
    for plot in _state.WORLD.plots.values():
        if plot.owner != player:
            continue
        region = region_for_plot(_state.WORLD, plot.plot_id) or ""
        if not region:
            continue
        plots_by_region.setdefault(region, []).append(str(plot.plot_id))
    # Building registry on player plots — surfaces which plots already have a dock/waystation.
    player_plot_buildings: dict[str, list[str]] = {}
    for row in _state.WORLD.plot_buildings:
        if str(row.get("party")) != str(player):
            continue
        bid = str(row.get("building_id"))
        if bid not in ("dock", "waystation"):
            continue
        if int(row.get("completes_at_tick", 0)) > int(_state.WORLD.tick):
            continue
        player_plot_buildings.setdefault(str(row["plot_id"]), []).append(bid)
    vessel_qty = int(_state.WORLD.inventory.qty(player, MaterialId("vessel")))
    return {
        "ok": True,
        "regions": all_region_ids(),
        "routes": routes_out,
        "player": {
            "plots_by_region": plots_by_region,
            "operating_buildings_by_plot": player_plot_buildings,
            "vessel_qty": vessel_qty,
            "route_revenue_today_cents": route_revenue_by_party_today(_state.WORLD, player),
            "route_revenue_previous_day_cents": route_revenue_by_party_previous_day(
                _state.WORLD, player
            ),
        },
    }


@router.post("/routes/register")
def post_register_route(
    party: Annotated[str, Query()],
    plot_id: Annotated[str, Query()],
    from_region: Annotated[str, Query()],
    to_region: Annotated[str, Query()],
    fee_per_tile_cents: Annotated[int, Query()],
) -> dict:
    from realm.actions import register_route as _register_route

    r = _register_route(
        _state.WORLD,
        PartyId(party),
        PlotId(plot_id),
        from_region,
        to_region,
        fee_per_tile_cents,
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/routes/revise_fee")
def post_revise_route_fee(
    party: Annotated[str, Query()],
    route_key: Annotated[str, Query()],
    fee_per_tile_cents: Annotated[int, Query()],
) -> dict:
    from realm.actions import revise_route_fee

    r = revise_route_fee(_state.WORLD, PartyId(party), route_key, fee_per_tile_cents)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/plot/harvest")
def post_plot_harvest(
    party: Annotated[str, Query()],
    plot_id: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
) -> dict:
    r = harvest_plot_output_stock(_state.WORLD, PartyId(party), PlotId(plot_id), material, qty)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return {"ok": True}


@router.post("/trade/p2p")
def post_trade_p2p(
    seller: Annotated[str, Query()],
    buyer: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    total_price_cents: Annotated[int, Query()],
    idempotency_key: Annotated[str | None, Query()] = None,
) -> dict:
    r = p2p_trade(
        _state.WORLD,
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


@router.get("/business")
def get_business_registry() -> dict:
    """Snapshot of the world's registered businesses."""
    from realm.world import _business_registry_public

    return {"ok": True, "tick": _state.WORLD.tick, "registry": _business_registry_public(_state.WORLD)}


@router.post("/business/register")
def post_business_register(body: Annotated[dict, Body()]) -> dict:
    party_raw = body.get("party", "player")
    name_raw = body.get("name") or body.get("business_name")
    description_raw = body.get("description") or ""
    if not isinstance(name_raw, str) or not name_raw:
        raise HTTPException(status_code=400, detail="name is required")
    template_raw = body.get("template_id")
    plot_ids_raw = body.get("registered_plot_ids") or body.get("plot_ids")
    if template_raw is not None:
        if not isinstance(plot_ids_raw, list) or not plot_ids_raw:
            raise HTTPException(
                status_code=400,
                detail="registered_plot_ids (non-empty list) required with template_id",
            )
        r = register_business(
            _state.WORLD,
            PartyId(str(party_raw)),
            str(name_raw),
            str(description_raw),
            template_id=str(template_raw),
            registered_plot_ids=tuple(str(x) for x in plot_ids_raw),
        )
    else:
        r = register_business(
            _state.WORLD, PartyId(str(party_raw)), str(name_raw), str(description_raw)
        )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/construction/quotes")
def post_construction_quotes(body: Annotated[dict, Body()]) -> dict:
    from realm.actions.construction_actions import request_construction_quotes

    party_raw = body.get("party", "player")
    plot_raw = body.get("plot_id")
    building_raw = body.get("building_id")
    mode = str(body.get("material_responsibility", "contractor"))
    if not plot_raw or not building_raw:
        raise HTTPException(status_code=400, detail="plot_id and building_id required")
    rows = request_construction_quotes(
        _state.WORLD,
        PartyId(str(party_raw)),
        PlotId(str(plot_raw)),
        str(building_raw),
        mode,
    )
    return {"ok": True, "tick": _state.WORLD.tick, "quotes": rows}


@router.post("/construction/accept")
def post_construction_accept(body: Annotated[dict, Body()]) -> dict:
    from realm.actions.construction_actions import accept_construction_quote

    r = accept_construction_quote(
        _state.WORLD,
        PartyId(str(body.get("client", "player"))),
        PartyId(str(body.get("contractor"))),
        PlotId(str(body.get("plot_id"))),
        str(body.get("building_id", "")),
        int(body.get("quoted_price_cents", 0)),
        str(body.get("material_responsibility", "contractor")),
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/science/chemistry")
def get_science_chemistry() -> dict:
    from realm.science import chemistry

    return {
        "ok": True,
        "elements": list(chemistry.ELEMENT_SYMBOLS),
        "reactions": chemistry.REACTIONS_PUBLIC,
    }


@router.post("/plots/{plot_id}/lab/bench")
def post_lab_bench(
    plot_id: str,
    body: Annotated[dict, Body()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    from realm.actions.science_actions import run_laboratory_bench

    r = run_laboratory_bench(
        _state.WORLD,
        PartyId(party),
        PlotId(plot_id),
        str(body.get("material_a", "")),
        str(body.get("material_b", "")),
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


# ─────────────────── Sprint 5 — Phase B: sub-accounts ───────────────────


@router.get("/accounts")
def get_accounts(party: Annotated[str, Query()] = "player") -> dict:
    from realm.core.sub_accounts import party_accounts_view

    return {
        "ok": True,
        "tick": _state.WORLD.tick,
        "party": party,
        "accounts": party_accounts_view(_state.WORLD, PartyId(party)),
    }


@router.get("/accounts/{label}/history")
def get_account_history(
    label: str,
    party: Annotated[str, Query()] = "player",
    limit: Annotated[int, Query()] = 20,
) -> dict:
    from realm.core.sub_accounts import sub_account_history

    return {
        "ok": True,
        "tick": _state.WORLD.tick,
        "party": party,
        "label": label,
        "transactions": sub_account_history(_state.WORLD, PartyId(party), label, limit=limit),
    }


@router.post("/accounts/create")
def post_account_create(body: Annotated[dict, Body()]) -> dict:
    from realm.core.sub_accounts import create_sub_account

    party_raw = body.get("party", "player")
    label_raw = body.get("label")
    if not isinstance(label_raw, str) or not label_raw.strip():
        raise HTTPException(status_code=400, detail="label is required")
    r = create_sub_account(_state.WORLD, PartyId(str(party_raw)), str(label_raw))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


# ─────────────────── Sprint 5 — Phase C: NPC bank ───────────────────


@router.post("/accounts/transfer")
def post_account_transfer(body: Annotated[dict, Body()]) -> dict:
    from realm.core.sub_accounts import transfer_own

    party_raw = body.get("party", "player")
    from_label = body.get("from_label") or body.get("from")
    to_label = body.get("to_label") or body.get("to")
    cents = body.get("cents") or body.get("amount_cents") or 0
    if not isinstance(from_label, str) or not isinstance(to_label, str):
        raise HTTPException(status_code=400, detail="from_label and to_label are required")
    try:
        cents_int = int(cents)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="cents must be an integer")
    r = transfer_own(_state.WORLD, PartyId(str(party_raw)), str(from_label), str(to_label), cents_int)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


# ─────────────────── Sprint 4 — Phase B: analytics products ───────────────────


@router.get("/roads")
def get_roads() -> dict:
    return {"ok": True, "tick": _state.WORLD.tick, "segments": all_roads_public(_state.WORLD)}


@router.post("/roads/build")
def post_road_build(body: Annotated[dict, Body()]) -> dict:
    party_raw = body.get("party", "player")
    from_plot = body.get("from_plot") or body.get("from_plot_id")
    to_plot = body.get("to_plot") or body.get("to_plot_id")
    if not isinstance(from_plot, str) or not isinstance(to_plot, str):
        raise HTTPException(status_code=400, detail="from_plot and to_plot are required")
    r = build_road(_state.WORLD, PartyId(str(party_raw)), PlotId(from_plot), PlotId(to_plot))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/roads/{segment_id}/toll")
def post_road_toll(segment_id: str, body: Annotated[dict, Body()]) -> dict:
    party_raw = body.get("party", "player")
    toll = body.get("toll_rate_pct")
    if toll is None:
        toll = body.get("toll_pct")
    try:
        toll_i = int(toll)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="toll_rate_pct must be an integer")
    r = set_road_toll(_state.WORLD, PartyId(str(party_raw)), str(segment_id), toll_i)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/buildings/{instance_id}/auto_list")
def post_building_auto_list(instance_id: str, body: Annotated[dict, Body()]) -> dict:
    """Sprint 6 — Phase D.2: toggle auto-listing of production output."""
    from realm.production import set_building_auto_list

    party_raw = body.get("party", "player")
    enabled = bool(body.get("enabled", False))
    r = set_building_auto_list(_state.WORLD, PartyId(str(party_raw)), str(instance_id), enabled)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)

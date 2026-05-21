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
    fire_laborer,
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
from realm.population.employment import (
    cancel_job_opening,
    post_job_opening,
)
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
    return {"ok": True, "plot_id": plot_id, "owner": str(party)}


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
    """Regional power market status for a single plot."""
    from realm.infrastructure.power_grid import get_plot_power_info

    pid = PlotId(plot_id)
    if _state.WORLD.plots.get(pid) is None:
        raise HTTPException(status_code=404, detail="unknown plot")
    return get_plot_power_info(_state.WORLD, pid)


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
    # Auto-place seeded blueprint (settlers, scripts). Players use POST /plots/{id}/place.
    r = build_on_plot(_state.WORLD, PartyId(party), PlotId(plot_id), building_id, build_mode=build_mode)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.get("/blueprints")
def get_blueprints(party: Annotated[str, Query()] = "player") -> dict:
    from realm.actions.blueprint_actions import blueprints_visible_to

    return {"blueprints": blueprints_visible_to(_state.WORLD, PartyId(party))}


@router.get("/blueprints/{blueprint_id}")
def get_blueprint(blueprint_id: str) -> dict:
    bp = _state.WORLD.blueprints.get(blueprint_id)
    if bp is None:
        raise HTTPException(status_code=404, detail="blueprint not found")
    from realm.production.blueprints import blueprint_public_dict

    return blueprint_public_dict(bp)


@router.post("/materials/register")
def post_register_material(body: dict) -> dict:
    from realm.actions.custom_recipe_actions import register_material_action

    party = PartyId(str(body.get("party", "player")))
    r = register_material_action(
        _state.WORLD,
        party,
        str(body.get("display_name", "")),
        str(body.get("category", "processed")),
        str(body.get("material_id", "")),
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/recipes/create")
def post_create_custom_recipe(body: dict) -> dict:
    from realm.actions.custom_recipe_actions import create_custom_recipe_action

    party = PartyId(str(body.get("party", "player")))
    inputs_raw = body.get("inputs") or {}
    outputs_raw = body.get("outputs") or {}
    inputs = {str(k): int(v) for k, v in inputs_raw.items()} if isinstance(inputs_raw, dict) else {}
    outputs = {str(k): int(v) for k, v in outputs_raw.items()} if isinstance(outputs_raw, dict) else {}
    r = create_custom_recipe_action(
        _state.WORLD,
        party,
        str(body.get("display_name", "")),
        inputs,
        outputs,
        int(body.get("duration_ticks", 60)),
        int(body.get("labor_cents", 0)),
        str(body.get("requires_building_id", "")),
        is_public=bool(body.get("is_public", False)),
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/blueprints/create")
def post_create_blueprint(body: dict) -> dict:
    from realm.actions.blueprint_actions import create_blueprint

    party = PartyId(str(body.get("party", "player")))
    r = create_blueprint(
        _state.WORLD,
        party,
        str(body.get("name", "")),
        str(body.get("description", "")),
        int(body.get("footprint_w", 1)),
        int(body.get("footprint_h", 1)),
        dict(body.get("construction_materials") or {}),
        int(body.get("construction_labor_cents", 0)),
        int(body.get("construction_ticks", 0)),
        list(body.get("enabled_recipe_ids") or []),
        int(body.get("maintenance_interval_ticks", 0)),
        dict(body.get("maintenance_materials") or {}),
        int(body.get("maintenance_grace_ticks", 0)),
        bool(body.get("is_public", False)),
        int(body.get("license_fee_cents", 0)),
        str(body.get("category", "custom")),
        list(body.get("terrain_requirements") or []),
        bool(body.get("requires_coastal", False)),
        bool(body.get("requires_power", False)),
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/plots/{plot_id}/place")
def post_place_blueprint(plot_id: str, body: dict) -> dict:
    from realm.actions.blueprint_actions import place_blueprint

    party = PartyId(str(body.get("party", "player")))
    r = place_blueprint(
        _state.WORLD,
        party,
        PlotId(plot_id),
        str(body.get("blueprint_id", "")),
        int(body.get("grid_x", 0)),
        int(body.get("grid_y", 0)),
        str(body.get("build_mode", "turnkey")),
        sub_plot_id=body.get("sub_plot_id"),
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/plots/{plot_id}/place-roads")
def post_place_road_path(plot_id: str, body: dict) -> dict:
    from realm.actions.blueprint_actions import place_road_path

    party = PartyId(str(body.get("party", "player")))
    cells_raw = body.get("cells", [])
    cells: list[tuple[int, int]] = []
    if isinstance(cells_raw, list):
        for item in cells_raw:
            if isinstance(item, dict):
                cells.append(
                    (
                        int(item.get("grid_x", item.get("x", 0))),
                        int(item.get("grid_y", item.get("y", 0))),
                    )
                )
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                cells.append((int(item[0]), int(item[1])))
    r = place_road_path(
        _state.WORLD,
        party,
        PlotId(plot_id),
        cells,
        str(body.get("build_mode", "turnkey")),
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("reason", "error"))
    return dict(r)


@router.get("/plots/{plot_id}/grid")
def get_plot_grid(plot_id: str) -> dict:
    from realm.actions.blueprint_actions import plot_grid_state

    return plot_grid_state(_state.WORLD, PlotId(plot_id))


@router.get("/plots/{plot_id}/available_positions/{blueprint_id}")
def get_available_positions(plot_id: str, blueprint_id: str) -> dict:
    from realm.actions.blueprint_actions import available_positions

    return {
        "positions": available_positions(_state.WORLD, PlotId(plot_id), blueprint_id)
    }


@router.get("/plots/{plot_id}/value")
def get_plot_value(plot_id: str) -> dict:
    from realm.world.real_estate import plot_market_summary

    return plot_market_summary(_state.WORLD, PlotId(plot_id))


@router.get("/plots/market")
def get_plots_market() -> dict:
    return {"listings": dict(_state.WORLD.scenario_state.get("plots_for_sale") or {})}


@router.post("/plots/{plot_id}/list-for-sale")
def post_list_plot_for_sale(plot_id: str, body: dict) -> dict:
    from realm.world.real_estate import list_plot_for_sale_market

    party = PartyId(str(body.get("party", "player")))
    ask = body.get("ask_price_cents")
    r = list_plot_for_sale_market(
        _state.WORLD,
        party,
        PlotId(plot_id),
        int(ask) if ask is not None else None,
    )
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=str(r["reason"]))
    return dict(r)


@router.post("/plots/{plot_id}/buy")
def post_buy_plot(plot_id: str, body: dict) -> dict:
    from realm.world.real_estate import buy_plot_market

    party = PartyId(str(body.get("party", "player")))
    r = buy_plot_market(_state.WORLD, party, PlotId(plot_id))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=str(r["reason"]))
    return dict(r)


@router.get("/plots/market/demand")
def get_plot_demand() -> dict:
    return {
        "plot_demand_scores": dict(
            _state.WORLD.scenario_state.get("plot_demand_scores") or {}
        ),
        "plot_npc_bids": dict(_state.WORLD.scenario_state.get("plot_npc_bids") or {}),
    }


@router.post("/plots/{plot_id}/subdivide")
def post_subdivide_plot(plot_id: str, body: dict) -> dict:
    from realm.actions.plot_actions import subdivide_plot

    party = PartyId(str(body.get("party", "player")))
    parts = body.get("partitions") or []
    r = subdivide_plot(_state.WORLD, party, PlotId(plot_id), list(parts))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.get("/plots/{plot_id}/sub-plots")
def get_sub_plots(plot_id: str) -> dict:
    subs = [
        {
            "sub_plot_id": sp.sub_plot_id,
            "parent_plot_id": sp.parent_plot_id,
            "owner": sp.owner,
            "grid_x": sp.grid_x,
            "grid_y": sp.grid_y,
            "grid_w": sp.grid_w,
            "grid_h": sp.grid_h,
            "area_sq_metres": sp.area_sq_metres,
            "listed_for_sale": sp.listed_for_sale,
            "ask_price_cents": sp.ask_price_cents,
        }
        for sp in _state.WORLD.sub_plots.values()
        if sp.parent_plot_id == plot_id
    ]
    return {"sub_plots": subs}


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


@router.get("/workflow")
def get_workflow(party: Annotated[str, Query()] = "player") -> dict:
    from realm.infrastructure.building_workflow import workflow_public_dict

    return {"ok": True, **workflow_public_dict(_state.WORLD, PartyId(party))}


@router.get("/workflow/building")
def get_workflow_building(
    instance_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    from realm.infrastructure.building_workflow import get_building_routing

    r = get_building_routing(_state.WORLD, PartyId(party), instance_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/workflow/building")
def post_workflow_building(body: dict) -> dict:
    from realm.infrastructure.building_workflow import set_building_routing

    party = PartyId(str(body.get("party", "player")))
    instance_id = str(body.get("instance_id", ""))
    inp = body.get("input") or {}
    out = body.get("output") or {}
    if not isinstance(inp, dict) or not isinstance(out, dict):
        raise HTTPException(status_code=400, detail="input and output must be objects")
    r = set_building_routing(
        _state.WORLD,
        party,
        instance_id,
        {str(k): str(v) for k, v in inp.items()},
        {str(k): str(v) for k, v in out.items()},
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/workflow/warehouse")
def post_workflow_warehouse(body: dict) -> dict:
    from realm.infrastructure.building_workflow import set_warehouse_rule

    party = PartyId(str(body.get("party", "player")))
    plot_id = PlotId(str(body.get("plot_id", "")))
    material = str(body.get("material", ""))
    r = set_warehouse_rule(
        _state.WORLD,
        party,
        plot_id,
        material,
        enabled=bool(body.get("enabled", False)),
        target_qty=int(body.get("target_qty", 0)),
        max_price_cents=int(body.get("max_price_cents", 0)),
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


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


def _job_opening_public_dict(op: object) -> dict:
    return {
        "opening_id": str(getattr(op, "opening_id", "")),
        "employer": str(getattr(op, "employer", "")),
        "plot_id": str(getattr(op, "plot_id", "")),
        "skill_min": int(getattr(op, "skill_min", 0)),
        "wage_per_day_cents": int(getattr(op, "wage_per_day_cents", 0)),
        "posted_at_tick": int(getattr(op, "posted_at_tick", 0)),
        "filled_by": getattr(op, "filled_by", None),
        "cpi_indexed": bool(getattr(op, "cpi_indexed", False)),
    }


@router.post("/jobs/openings")
def create_job_opening(
    employer: Annotated[str, Query()],
    plot_id: Annotated[str, Query()],
    skill_min: Annotated[int, Query()] = 0,
    wage_per_day_cents: Annotated[int, Query()] = 800,
    cpi_indexed: Annotated[bool, Query()] = False,
) -> dict:
    r = post_job_opening(
        _state.WORLD,
        PartyId(employer),
        PlotId(plot_id),
        skill_min=skill_min,
        wage_per_day_cents=wage_per_day_cents,
        cpi_indexed=cpi_indexed,
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.delete("/jobs/openings/{opening_id}")
def delete_job_opening(
    opening_id: str,
    employer: Annotated[str, Query()],
) -> dict:
    r = cancel_job_opening(_state.WORLD, PartyId(employer), opening_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/jobs/openings")
def list_job_openings(employer: Annotated[str | None, Query()] = None) -> dict:
    w = _state.WORLD
    openings = [_job_opening_public_dict(o) for o in w.job_openings]
    if employer:
        openings = [o for o in openings if o.get("employer") == employer]
    return {"openings": openings}


@router.get("/jobs/openings/catalog")
def job_openings_catalog() -> dict:
    return {"catalog": hire_catalog_public()}


@router.get("/laborers")
def list_laborers(
    town: Annotated[str | None, Query()] = None,
    employed: Annotated[bool | None, Query()] = None,
    skill_min: Annotated[int, Query()] = 0,
) -> dict:
    w = _state.WORLD
    result: list[dict] = []
    for lab_id, lab in w.laborers.items():
        if employed is not None and (lab.employer is not None) != employed:
            continue
        if int(lab.skill_level) < int(skill_min):
            continue
        if town and str(lab.home_town or "") != town:
            continue
        result.append(
            {
                "laborer_id": lab_id,
                "display_name": lab.display_name,
                "skill_level": int(lab.skill_level),
                "health": float(lab.health),
                "needs": {k: float(v) for k, v in lab.needs.items()},
                "home_town": lab.home_town,
                "employed": lab.employer is not None,
                "employer": str(lab.employer) if lab.employer else None,
                "wage_per_day_cents": int(getattr(lab, "wage_per_day_cents", 0) or 0),
            }
        )
    return {"laborers": result, "count": len(result)}


@router.post("/hire/fire")
def post_hire_fire(
    employer: Annotated[str, Query()],
    laborer_id: Annotated[str, Query()],
) -> dict:
    r = fire_laborer(_state.WORLD, PartyId(employer), laborer_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@router.post("/buildings/{instance_id}/demolish")
def post_demolish_building(
    instance_id: str,
    party: Annotated[str, Query()] = "player",
) -> dict:
    from realm.actions.blueprint_actions import demolish_building

    r = demolish_building(_state.WORLD, PartyId(party), instance_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
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


@router.get("/shipping/estimate")
def shipping_estimate(
    from_plot: Annotated[str, Query()],
    to_plot: Annotated[str, Query()],
    qty: Annotated[int, Query()] = 1,
) -> dict:
    """Preview bulk shipping cost before committing."""
    from realm.infrastructure.movement import compute_shipping_fee

    return compute_shipping_fee(
        _state.WORLD, PlotId(from_plot), PlotId(to_plot), qty
    )


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
        ROUTE_DAILY_CAPACITY,
        list_route_operators,
        route_revenue_by_party_previous_day,
        route_revenue_by_party_today,
    )

    operators = _state.WORLD.scenario_state.get("route_operators") or {}
    route_volume = _state.WORLD.scenario_state.get("route_daily_volume") or {}
    routes_out: list[dict] = []
    for key in sorted(operators.keys()):
        entries = list_route_operators(_state.WORLD, key)
        a, b = key.split(":", 1)
        vol = route_volume.get(key) if isinstance(route_volume, dict) else None
        routes_out.append(
            {
                "key": key,
                "region_a": a,
                "region_b": b,
                "units_shipped_today": int((vol or {}).get("units_shipped_today", 0)),
                "daily_capacity": int((vol or {}).get("daily_capacity", ROUTE_DAILY_CAPACITY)),
                "operators": [
                    {
                        "party": str(e.get("operator_party")),
                        "plot_id": str(e.get("operator_plot")),
                        "building": str(e.get("building")),
                        "fee_per_tile_cents": int(e.get("fee_per_tile_cents", 0)),
                        "registered_at_tick": int(e.get("registered_at_tick", 0)),
                        "units_shipped_today": int(e.get("units_shipped_today", 0)),
                        "daily_capacity": int(e.get("daily_capacity", ROUTE_DAILY_CAPACITY)),
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


@router.get("/business/entity/{business_id}")
def get_business_entity_detail(business_id: str) -> dict:
    from realm.economy.businesses import business_shareholders, ownership_pct_bps_sold

    w = _state.WORLD
    biz = w.businesses.get(business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="unknown business")
    sold = ownership_pct_bps_sold(w, business_id)
    return {
        "ok": True,
        "business_id": biz.business_id,
        "business_name": biz.business_name,
        "owner_party": str(biz.owner_party),
        "equity": {
            "pct_sold_bps": sold,
            "pct_founder_retains_bps": max(0, 10_000 - sold),
            "shareholders": business_shareholders(w, business_id),
        },
    }


@router.post("/businesses/register")
def post_businesses_register(body: Annotated[dict, Body()]) -> dict:
    """Alias of ``POST /business/register`` for UI route parity."""
    return post_business_register(body)


@router.get("/businesses/templates")
def get_businesses_templates() -> dict:
    from realm.economy.businesses import BUSINESS_TEMPLATES

    rows = [
        {"template_id": tpl.template_id, "label": tpl.display_name, "kind": tpl.type_tag}
        for tid, tpl in sorted(BUSINESS_TEMPLATES.items(), key=lambda kv: kv[0])
    ]
    return {"ok": True, "tick": _state.WORLD.tick, "templates": rows}


@router.get("/businesses/mine")
def get_businesses_mine(party: Annotated[str, Query()] = "player") -> dict:
    w = _state.WORLD
    pid = PartyId(party)
    rows = [b for b in w.businesses.values() if b.owner_party == pid]
    return {
        "ok": True,
        "tick": w.tick,
        "party": party,
        "businesses": [
            {
                "business_id": b.business_id,
                "business_name": b.business_name,
                "status": b.status,
                "business_type_tag": b.business_type_tag,
            }
            for b in rows
        ],
    }


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


@router.post("/construction/order")
def post_construction_order(body: Annotated[dict, Body()]) -> dict:
    """Alias of ``POST /construction/accept`` (place a construction order from a quote)."""
    return post_construction_accept(body)


@router.get("/construction/orders")
def get_construction_orders(
    party: Annotated[str, Query()] = "player",
    role: Annotated[str, Query()] = "any",
) -> dict:
    """List construction orders involving ``party`` (client, contractor, or any)."""
    w = _state.WORLD
    ps = str(party)
    role_l = str(role).lower()
    if role_l not in ("any", "client", "contractor"):
        raise HTTPException(status_code=400, detail="role must be any, client, or contractor")
    out: list[dict] = []
    for c in w.contracts:
        if c.get("kind") != "construction_order":
            continue
        client = str(c.get("client_party", ""))
        contractor = str(c.get("contractor_party", ""))
        if role_l == "client" and client != ps:
            continue
        if role_l == "contractor" and contractor != ps:
            continue
        if role_l == "any" and ps not in (client, contractor):
            continue
        out.append(dict(c))
    return {"ok": True, "tick": w.tick, "party": party, "role": role_l, "orders": out}


@router.get("/science/chemistry")
def get_science_chemistry() -> dict:
    from realm.science import chemistry

    return {
        "ok": True,
        "elements": list(chemistry.ELEMENT_SYMBOLS),
        "reactions": chemistry.REACTIONS_PUBLIC,
    }


@router.get("/science/elements")
def get_science_elements() -> dict:
    from realm.science import chemistry

    return {"ok": True, "elements": list(chemistry.ELEMENT_SYMBOLS)}


@router.get("/science/reactions/discovered")
def get_science_reactions_discovered(party: Annotated[str, Query()] = "player") -> dict:
    from realm.science import chemistry

    w = _state.WORLD
    book = w.party_recipe_books.get(party, set())
    discovered = [r for r in chemistry.REACTIONS_PUBLIC if str(r.get("output", "")) in book]
    return {"ok": True, "tick": w.tick, "party": party, "reactions": discovered}


@router.post("/science/experiment")
def post_science_experiment(body: Annotated[dict, Body()]) -> dict:
    from realm.actions.science_actions import run_laboratory_bench

    plot_raw = body.get("plot_id")
    if not plot_raw:
        raise HTTPException(status_code=400, detail="plot_id is required in the JSON body")
    party_raw = body.get("party", "player")
    r = run_laboratory_bench(
        _state.WORLD,
        PartyId(str(party_raw)),
        PlotId(str(plot_raw)),
        str(body.get("material_a", "")),
        str(body.get("material_b", "")),
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


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

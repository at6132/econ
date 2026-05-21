"""Serialize / deserialize full World for SQLite persistence.

Snapshot ``version`` is ``14`` (older rows still load). Nested dict/list values are deep-copied on dump
so JSON round-trips do not share mutable subgraphs with the live ``World``.

``load_world`` uses defaults via ``dict.get`` so older SQLite/JSON rows remain loadable when new
fields are additive (e.g. ``market_bids``, ``best_bids_cents`` in history).
"""

from __future__ import annotations

import copy
import json
from typing import Any

from realm.production.decay import BUILDING_CONDITION_FULL_BPS
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import Inventory
from realm.core.ledger import Ledger
from realm.economy.markets import AskOrder, BidOrder, _sort_asks, _sort_bids
from realm.world import (
    ActiveProduction,
    BusinessRecord,
    InTransit,
    RoadSegment,
    SubsurfaceRoll,
    SurveyReport,
    World,
    generate_plots,
)
from realm.world.terrain import Terrain

# Bump when serialized shape or semantics change; loaders accept older versions they understand.
SNAPSHOT_VERSION = 15


def _blueprint_public_dict(bp: object) -> dict[str, Any]:
    from realm.production.blueprints import blueprint_public_dict

    return blueprint_public_dict(bp)  # type: ignore[arg-type]


def _json_safe_key(key: Any) -> str:
    if isinstance(key, str):
        return key
    if isinstance(key, tuple):
        return ",".join(str(part) for part in key)
    return str(key)


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {_json_safe_key(k): _json_safe_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_json_safe_value(v) for v in value)
    return value


def _scenario_state_for_snapshot(state: dict[str, Any] | None) -> dict[str, Any]:
    """Drop ephemeral ``_`` keys and coerce dict keys to JSON-safe strings."""
    out: dict[str, Any] = {}
    for key, val in (state or {}).items():
        if str(key).startswith("_"):
            continue
        out[_json_safe_key(key)] = _json_safe_value(val)
    return out


def _max_building_instance_seq_from_rows(rows: list[dict[str, Any]]) -> int:
    m = 0
    for row in rows:
        sid = str(row.get("instance_id") or "")
        if len(sid) == 7 and sid.startswith("b"):
            try:
                m = max(m, int(sid[1:], 10))
            except ValueError:
                pass
    return m


def dump_world(world: World) -> dict[str, Any]:
    plots_out: dict[str, Any] = {}
    from realm.production.recipe_sites import plot_is_coastal
    from realm.world.plot_scale import plot_world_cells_tuple

    for pid, p in world.plots.items():
        plots_out[str(pid)] = {
            "x": p.x,
            "y": p.y,
            "world_cells": [{"x": cx, "y": cy} for cx, cy in plot_world_cells_tuple(p)],
            "terrain": p.terrain.value,
            "is_coastal": plot_is_coastal(world, p),
            "owner": str(p.owner) if p.owner else None,
            "surveyed": p.surveyed,
            "deep_surveyed": getattr(p, "deep_surveyed", False),
            "subsurface": {
                "iron_ore_grade": p.subsurface.iron_ore_grade,
                "copper_ore_grade": p.subsurface.copper_ore_grade,
                "clay_grade": p.subsurface.clay_grade,
                "coal_grade": p.subsurface.coal_grade,
                "sulfur_grade": p.subsurface.sulfur_grade,
                "saltpeter_grade": p.subsurface.saltpeter_grade,
                "tin_grade": p.subsurface.tin_grade,
                "lead_grade": p.subsurface.lead_grade,
                "phosphate_grade": p.subsurface.phosphate_grade,
                "silica_grade": p.subsurface.silica_grade,
                "platinum_grade": p.subsurface.platinum_grade,
                "oil_shale_grade": p.subsurface.oil_shale_grade,
                "rare_earth_grade": p.subsurface.rare_earth_grade,
            },
        }
    asks: dict[str, list[dict[str, Any]]] = {}
    for k, lst in world.market_asks_by_material.items():
        asks[k] = [
            {
                "order_id": o.order_id,
                "party": str(o.party),
                "material": str(o.material),
                "qty": o.qty,
                "price_per_unit_cents": o.price_per_unit_cents,
                "posted_at_tick": int(getattr(o, "posted_at_tick", 0)),
                "iceberg_peak": o.iceberg_peak,
                "iceberg_hidden_qty": o.iceberg_hidden_qty,
                "min_counterparty_honored": o.min_counterparty_honored,
            }
            for o in lst
        ]
    bids: dict[str, list[dict[str, Any]]] = {}
    for k, lst in world.market_bids_by_material.items():
        bids[k] = [
            {
                "order_id": b.order_id,
                "party": str(b.party),
                "material": str(b.material),
                "qty": b.qty,
                "max_price_per_unit_cents": b.max_price_per_unit_cents,
                "posted_at_tick": int(getattr(b, "posted_at_tick", 0)),
                "escrow_cents": b.escrow_cents,
                "iceberg_peak": b.iceberg_peak,
                "iceberg_hidden_qty": b.iceberg_hidden_qty,
                "min_counterparty_honored": b.min_counterparty_honored,
            }
            for b in lst
        ]
    inv: dict[str, dict[str, object]] = {}
    for party in sorted(world.inventory.parties_with_stock_rows(), key=str):
        party_inv: dict[str, object] = {}
        for mat, raw in world.inventory.stock.get(party, {}).items():
            from realm.core.inventory import _normalize_bucket

            bucket = _normalize_bucket(raw)
            if len(bucket) == 1 and "standard" in bucket:
                party_inv[str(mat)] = int(bucket["standard"])
            elif bucket:
                party_inv[str(mat)] = dict(bucket)
        inv[str(party)] = party_inv
    return {
        "version": SNAPSHOT_VERSION,
        "seed": world.seed,
        "tick": world.tick,
        "next_production_seq": world.next_production_seq,
        "next_shipment_seq": world.next_shipment_seq,
        "next_order_seq": world.next_order_seq,
        "next_contract_seq": world.next_contract_seq,
        "plots": plots_out,
        "ledger": {str(k): v for k, v in world.ledger.snapshot().items()},
        "inventory": inv,
        "parties": sorted([str(p) for p in world.parties]),
        "active_production": [
            {
                "run_id": a.run_id,
                "party": str(a.party),
                "plot_id": str(a.plot_id),
                "recipe_id": a.recipe_id,
                "ticks_remaining": a.ticks_remaining,
                "runs_remaining": int(getattr(a, "runs_remaining", 0)),
            }
            for a in world.active_production
        ],
        "in_transit": [
            {
                "shipment_id": s.shipment_id,
                "party": str(s.party),
                "material": str(s.material),
                "qty": s.qty,
                "dest_plot_id": str(s.dest_plot_id),
                "arrive_tick": s.arrive_tick,
                "from_plot_id": str(s.from_plot_id) if s.from_plot_id else None,
                "dest_dock_owner": s.dest_dock_owner,
                "inter_island": bool(s.inter_island),
            }
            for s in world.in_transit
        ],
        "market_asks": asks,
        "market_bids": bids,
        "reputation": copy.deepcopy(dict(world.reputation)),
        "contracts": [copy.deepcopy(c) for c in world.contracts],
        "event_log": [copy.deepcopy(e) for e in world.event_log],
        "world_feed_log": [copy.deepcopy(e) for e in world.world_feed_log],
        "plot_buildings": [copy.deepcopy(b) for b in world.plot_buildings],
        "placed_buildings": {
            iid: {
                "instance_id": pb.instance_id,
                "blueprint_id": pb.blueprint_id,
                "plot_id": pb.plot_id,
                "grid_x": pb.grid_x,
                "grid_y": pb.grid_y,
                "built_at_tick": pb.built_at_tick,
                "built_by": pb.built_by,
                "status": pb.status,
                "efficiency_pct": pb.efficiency_pct,
                "missed_maintenance_cycles": pb.missed_maintenance_cycles,
                "due_at_tick": pb.due_at_tick,
                "sub_plot_id": pb.sub_plot_id,
                "original_cost_cents": int(pb.original_cost_cents),
                "book_value_cents": int(pb.book_value_cents),
                "depreciation_rate_per_year": float(pb.depreciation_rate_per_year),
            }
            for iid, pb in world.placed_buildings.items()
        },
        "plot_placed_buildings": copy.deepcopy(dict(world.plot_placed_buildings)),
        "blueprints": {
            bid: copy.deepcopy(_blueprint_public_dict(bp))
            for bid, bp in world.blueprints.items()
        },
        "sub_plots": {
            sid: {
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
                "lease_rights": copy.deepcopy(sp.lease_rights),
            }
            for sid, sp in world.sub_plots.items()
        },
        "stub_hires": [copy.deepcopy(h) for h in world.stub_hires],
        "market_history": [copy.deepcopy(h) for h in world.market_history],
        "p2p_idempotency": {str(k): copy.deepcopy(dict(v)) for k, v in world.p2p_idempotency.items()},
        "scenario_id": world.scenario_id,
        "world_id": world.world_id,
        "world_name": world.world_name,
        "market_intel_expires_tick": world.market_intel_expires_tick,
        "next_building_instance_seq": world.next_building_instance_seq,
        "llm_agents": copy.deepcopy(dict(world.llm_agents)),
        "npc_messages_to_player": copy.deepcopy(list(world.npc_messages_to_player)),
        "llm_session_cost_micro_usd": world.llm_session_cost_micro_usd,
        "llm_session_input_tokens": world.llm_session_input_tokens,
        "llm_session_output_tokens": world.llm_session_output_tokens,
        "deployed_lua_sources": copy.deepcopy(dict(world.deployed_lua_sources)),
        "party_display_names": copy.deepcopy(dict(world.party_display_names)),
        "scenario_state": _scenario_state_for_snapshot(world.scenario_state),
        "use_plot_output_logistics": world.use_plot_output_logistics,
        "plot_output_stock": copy.deepcopy(dict(world.plot_output_stock)),
        "market_seller_registered": sorted(world.market_seller_registered),
        "party_recipe_books": {
            str(k): sorted(v) for k, v in world.party_recipe_books.items()
        },
        "building_maintenance": {
            str(k): {str(kk): int(vv) for kk, vv in v.items()}
            for k, v in world.building_maintenance.items()
        },
        "survey_reports": {
            rid: {
                "report_id": rep.report_id,
                "plot_id": str(rep.plot_id),
                "conducted_by": str(rep.conducted_by),
                "conducted_at_tick": int(rep.conducted_at_tick),
                "grades": dict(rep.grades),
                "survey_type": rep.survey_type,
                "is_deep": bool(rep.is_deep),
            }
            for rid, rep in world.survey_reports.items()
        },
        "next_report_seq": int(world.next_report_seq),
        "intel_listings": [copy.deepcopy(row) for row in world.intel_listings],
        "next_intel_listing_seq": int(world.next_intel_listing_seq),
        "plot_listings": [copy.deepcopy(row) for row in world.plot_listings],
        "next_plot_listing_seq": int(world.next_plot_listing_seq),
        "survey_authorizations": [
            copy.deepcopy(row) for row in world.survey_authorizations
        ],
        "liens": [copy.deepcopy(row) for row in world.liens],
        "next_lien_seq": int(world.next_lien_seq),
        "analytics_purchases": [copy.deepcopy(row) for row in world.analytics_purchases],
        "business_registry": {
            pid_s: {
                "party_id": str(rec.party_id),
                "business_name": rec.business_name,
                "description": rec.description,
                "registered_at_tick": int(rec.registered_at_tick),
            }
            for pid_s, rec in world.business_registry.items()
        },
        "road_segments": [
            {
                "segment_id": s.segment_id,
                "from_plot": str(s.from_plot),
                "to_plot": str(s.to_plot),
                "owner": str(s.owner),
                "built_at_tick": int(s.built_at_tick),
                "toll_rate_pct": int(s.toll_rate_pct),
                "condition_bps": int(getattr(s, "condition_bps", 10_000)),
                "last_maintenance_tick": int(getattr(s, "last_maintenance_tick", 0)),
            }
            for s in world.road_segments
        ],
        "next_road_segment_seq": int(world.next_road_segment_seq),
        "laborers": {
            lid: {
                "laborer_id": lab.laborer_id,
                "display_name": lab.display_name,
                "island_id": int(lab.island_id),
                "home_plot_id": str(lab.home_plot_id),
                "home_town": lab.home_town,
                "employer": str(lab.employer) if lab.employer is not None else None,
                "skill_level": int(lab.skill_level),
                "age_ticks": int(lab.age_ticks),
                "health": float(lab.health),
                "cash_cents": int(lab.cash_cents),
                "needs": {k: float(v) for k, v in lab.needs.items()},
                "employment_contract": lab.employment_contract,
                "wage_per_day_cents": int(getattr(lab, "wage_per_day_cents", 0) or 0),
                "migrating_to": lab.migrating_to,
                "migration_arrives_tick": int(lab.migration_arrives_tick),
                "last_needs_tick": int(lab.last_needs_tick),
            }
            for lid, lab in world.laborers.items()
        },
        "towns": {
            tid: {
                "town_id": t.town_id,
                "name": t.name,
                "island_id": int(t.island_id),
                "center_plot": str(t.center_plot),
                "residential_plots": [str(p) for p in t.residential_plots],
                "laborer_count": int(t.laborer_count),
                "store_plots": [str(p) for p in t.store_plots],
            }
            for tid, t in world.towns.items()
        },
        "store_inventories": {
            pid: {mid: int(qty) for mid, qty in inv.items()}
            for pid, inv in world.store_inventories.items()
        },
        "store_prices": {
            pid: {mid: int(px) for mid, px in prices.items()}
            for pid, prices in world.store_prices.items()
        },
        "store_revenue_today": {
            pid: int(c) for pid, c in world.store_revenue_today.items()
        },
        "job_openings": [
            {
                "opening_id": op.opening_id,
                "employer": str(op.employer),
                "plot_id": str(op.plot_id),
                "skill_min": int(op.skill_min),
                "wage_per_day_cents": int(op.wage_per_day_cents),
                "posted_at_tick": int(op.posted_at_tick),
                "filled_by": op.filled_by,
                "cpi_indexed": bool(getattr(op, "cpi_indexed", False)),
            }
            for op in world.job_openings
        ],
        "next_business_seq": int(world.next_business_seq),
        "business_entities": [
            {
                "business_id": ent.business_id,
                "owner_party": str(ent.owner_party),
                "business_name": ent.business_name,
                "business_type_tag": ent.business_type_tag,
                "description": ent.description,
                "registered_at_tick": int(ent.registered_at_tick),
                "registered_plot_ids": [str(p) for p in ent.registered_plot_ids],
                "sub_account_label": ent.sub_account_label,
                "status": ent.status,
                "suspension_reason": ent.suspension_reason,
                "public_profile": bool(ent.public_profile),
                "last_viability_check_tick": int(ent.last_viability_check_tick),
                "equity_contract_ids": list(getattr(ent, "equity_contract_ids", []) or []),
            }
            for ent in world.businesses.values()
        ],
        "next_nascent_settlement_seq": int(world.next_nascent_settlement_seq),
        "nascent_settlements": [
            {
                "nascent_id": ns.nascent_id,
                "island_id": int(ns.island_id),
                "anchor_plot_id": str(ns.anchor_plot_id),
                "member_plot_ids": [str(p) for p in ns.member_plot_ids],
                "resident_count": int(ns.resident_count),
                "consecutive_game_days": int(ns.consecutive_game_days),
                "last_checked_tick": int(ns.last_checked_tick),
            }
            for ns in world.nascent_settlements.values()
        ],
        "futures_orders": [
            {
                "order_id": o.order_id,
                "side": o.side,
                "poster": str(o.poster),
                "material": str(o.material),
                "qty": int(o.qty),
                "price_per_unit_cents": int(o.price_per_unit_cents),
                "delivery_tick": int(o.delivery_tick),
                "deposit_cents": int(o.deposit_cents),
                "status": str(o.status),
                "matched_with": o.matched_with,
                "posted_at_tick": int(o.posted_at_tick),
                "match_price_cents": o.match_price_cents,
            }
            for o in world.futures_orders
        ],
        "fx_orders": [
            {
                "order_id": o.order_id,
                "poster": str(o.poster),
                "sell_material": str(o.sell_material),
                "sell_qty": int(o.sell_qty),
                "buy_material": str(o.buy_material),
                "buy_qty_min": int(o.buy_qty_min),
                "posted_at_tick": int(o.posted_at_tick),
                "status": str(o.status),
                "expires_at_tick": int(o.expires_at_tick),
                "filled_sell_qty": int(getattr(o, "filled_sell_qty", 0)),
                "filled_buy_qty": int(getattr(o, "filled_buy_qty", 0)),
            }
            for o in world.fx_orders
        ],
        "issued_currencies": {
            k: {
                "currency_id": c.currency_id,
                "symbol": c.symbol,
                "name": c.name,
                "issuer_party": c.issuer_party,
                "business_id": c.business_id,
                "material_id": c.material_id,
                "reserve_ratio": float(c.reserve_ratio),
                "total_issued": int(c.total_issued),
                "reserve_cents": int(c.reserve_cents),
                "created_at_tick": int(c.created_at_tick),
                "status": str(c.status),
            }
            for k, c in world.issued_currencies.items()
        },
        "regional_advantages": {str(k): dict(v) for k, v in world.regional_advantages.items()},
        "grid_width": int(world.scenario_state.get("grid_width", 0)),
        "grid_height": int(world.scenario_state.get("grid_height", 0)),
        "world_cell_to_plot": {
            _json_safe_key(k): str(v)
            for k, v in (world.scenario_state.get("world_cell_to_plot") or {}).items()
        },
    }


def _snapshot_grid_size(saved_plots: dict[str, Any]) -> tuple[int, int]:
    max_x = 0
    max_y = 0
    for saved in saved_plots.values():
        cells = saved.get("world_cells")
        if cells:
            for c in cells:
                max_x = max(max_x, int(c["x"]))
                max_y = max(max_y, int(c["y"]))
        else:
            max_x = max(max_x, int(saved["x"]))
            max_y = max(max_y, int(saved["y"]))
    return max_x + 1, max_y + 1


def _plot_from_snapshot(pid_str: str, saved: dict[str, Any]) -> Plot:
    from realm.world.world import Plot

    cells_raw = saved.get("world_cells")
    if cells_raw:
        world_cells = tuple((int(c["x"]), int(c["y"])) for c in cells_raw)
        anchor_x = min(c[0] for c in world_cells)
        anchor_y = min(c[1] for c in world_cells)
    else:
        anchor_x = int(saved["x"])
        anchor_y = int(saved["y"])
        world_cells = ((anchor_x, anchor_y),)
    sub = saved.get("subsurface") or {}
    return Plot(
        plot_id=PlotId(pid_str),
        x=anchor_x,
        y=anchor_y,
        terrain=Terrain(saved["terrain"]),
        owner=PartyId(saved["owner"]) if saved.get("owner") else None,
        subsurface=SubsurfaceRoll(
            iron_ore_grade=float(sub.get("iron_ore_grade", 0)),
            copper_ore_grade=float(sub.get("copper_ore_grade", 0)),
            clay_grade=float(sub.get("clay_grade", 0)),
            coal_grade=float(sub.get("coal_grade", 0)),
            sulfur_grade=float(sub.get("sulfur_grade", 0)),
            saltpeter_grade=float(sub.get("saltpeter_grade", 0)),
            tin_grade=float(sub.get("tin_grade", 0)),
            lead_grade=float(sub.get("lead_grade", 0)),
            phosphate_grade=float(sub.get("phosphate_grade", 0)),
            silica_grade=float(sub.get("silica_grade", 0)),
            platinum_grade=float(sub.get("platinum_grade", 0)),
            oil_shale_grade=float(sub.get("oil_shale_grade", 0)),
            rare_earth_grade=float(sub.get("rare_earth_grade", 0)),
        ),
        surveyed=bool(saved.get("surveyed", False)),
        deep_surveyed=bool(saved.get("deep_surveyed", False)),
        world_cells=world_cells,
    )


def load_world(d: dict[str, Any]) -> World:
    ver = d.get("version", 1)
    if ver not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
        raise ValueError(f"unsupported snapshot version: {ver!r}")
    seed = int(d["seed"])
    saved_plots: dict[str, Any] = d["plots"]
    has_geometry = any(saved.get("world_cells") for saved in saved_plots.values())
    if has_geometry:
        plots = {PlotId(pid_str): _plot_from_snapshot(pid_str, saved) for pid_str, saved in saved_plots.items()}
    else:
        width, height = _snapshot_grid_size(saved_plots)
        if int(d.get("grid_width", 0)) > 0 and int(d.get("grid_height", 0)) > 0:
            width = int(d["grid_width"])
            height = int(d["grid_height"])
        plots = generate_plots(seed=seed, width=width, height=height)
        for pid_str, saved in saved_plots.items():
            pid = PlotId(pid_str)
            if pid not in plots:
                continue
            p = plots[pid]
            p.terrain = Terrain(saved["terrain"])
            p.owner = PartyId(saved["owner"]) if saved.get("owner") else None
            p.surveyed = bool(saved.get("surveyed", False))
            p.deep_surveyed = bool(saved.get("deep_surveyed", False))
            sub = saved.get("subsurface") or {}
            p.subsurface = SubsurfaceRoll(
                iron_ore_grade=float(sub.get("iron_ore_grade", 0)),
                copper_ore_grade=float(sub.get("copper_ore_grade", 0)),
                clay_grade=float(sub.get("clay_grade", 0)),
                coal_grade=float(sub.get("coal_grade", 0)),
                sulfur_grade=float(sub.get("sulfur_grade", 0)),
                saltpeter_grade=float(sub.get("saltpeter_grade", 0)),
                tin_grade=float(sub.get("tin_grade", 0)),
                lead_grade=float(sub.get("lead_grade", 0)),
                phosphate_grade=float(sub.get("phosphate_grade", 0)),
                silica_grade=float(sub.get("silica_grade", 0)),
                platinum_grade=float(sub.get("platinum_grade", 0)),
                oil_shale_grade=float(sub.get("oil_shale_grade", 0)),
                rare_earth_grade=float(sub.get("rare_earth_grade", 0)),
            )
    ledger = Ledger()
    for acc, bal in d["ledger"].items():
        ledger.balances[acc] = int(bal)
    inv = Inventory()
    for ps, mats in d["inventory"].items():
        party = PartyId(ps)
        if not mats:
            inv.ensure_party_bucket(party)
        else:
            for ms, q in mats.items():
                if isinstance(q, dict):
                    for qual, qty in q.items():
                        inv.add(party, MaterialId(ms), int(qty), quality=str(qual))
                else:
                    inv.add(party, MaterialId(ms), int(q))
    parties = {PartyId(p) for p in d["parties"]}
    active: list[ActiveProduction] = []
    for row in d.get("active_production", []):
        active.append(
            ActiveProduction(
                run_id=row["run_id"],
                party=PartyId(row["party"]),
                plot_id=PlotId(row["plot_id"]),
                recipe_id=row["recipe_id"],
                ticks_remaining=int(row["ticks_remaining"]),
                runs_remaining=int(row.get("runs_remaining", 0)),
            )
        )
    transit: list[InTransit] = []
    for row in d.get("in_transit", []):
        transit.append(
            InTransit(
                shipment_id=row["shipment_id"],
                party=PartyId(row["party"]),
                material=MaterialId(row["material"]),
                qty=int(row["qty"]),
                dest_plot_id=PlotId(row["dest_plot_id"]),
                arrive_tick=int(row["arrive_tick"]),
                from_plot_id=PlotId(row["from_plot_id"]) if row.get("from_plot_id") else None,
                dest_dock_owner=row.get("dest_dock_owner"),
                inter_island=bool(row.get("inter_island", False)),
            )
        )
    asks_map: dict[str, list[Any]] = {}
    for mat_key, rows in d.get("market_asks", {}).items():
        asks_map[mat_key] = [
            AskOrder(
                order_id=r["order_id"],
                party=PartyId(r["party"]),
                material=MaterialId(r["material"]),
                qty=int(r["qty"]),
                price_per_unit_cents=int(r["price_per_unit_cents"]),
                posted_at_tick=int(r.get("posted_at_tick", 0)),
                iceberg_peak=int(r.get("iceberg_peak", 0)),
                iceberg_hidden_qty=int(r.get("iceberg_hidden_qty", 0)),
                min_counterparty_honored=int(r.get("min_counterparty_honored", 0)),
                quality=str(r.get("quality", "standard")),
            )
            for r in rows
        ]
        _sort_asks(asks_map[mat_key])
    bids_map: dict[str, list[Any]] = {}
    for mat_key, rows in d.get("market_bids", {}).items():
        bids_map[mat_key] = [
            BidOrder(
                order_id=r["order_id"],
                party=PartyId(r["party"]),
                material=MaterialId(r["material"]),
                qty=int(r["qty"]),
                max_price_per_unit_cents=int(r["max_price_per_unit_cents"]),
                escrow_cents=int(r.get("escrow_cents", int(r["qty"]) * int(r["max_price_per_unit_cents"]))),
                posted_at_tick=int(r.get("posted_at_tick", 0)),
                iceberg_peak=int(r.get("iceberg_peak", 0)),
                iceberg_hidden_qty=int(r.get("iceberg_hidden_qty", 0)),
                min_counterparty_honored=int(r.get("min_counterparty_honored", 0)),
            )
            for r in rows
        ]
        _sort_bids(bids_map[mat_key])
    saved_bseq = int(d.get("next_building_instance_seq", 0))
    plot_buildings_m: list[dict[str, Any]] = []
    for raw in d.get("plot_buildings", []):
        plot_buildings_m.append(copy.deepcopy(dict(raw)))
    for row in plot_buildings_m:
        if row.get("condition_bps") is None:
            row["condition_bps"] = BUILDING_CONDITION_FULL_BPS
    m_from_ids = _max_building_instance_seq_from_rows(plot_buildings_m)
    assign_counter = max(saved_bseq, m_from_ids)
    for row in plot_buildings_m:
        if not row.get("instance_id"):
            assign_counter += 1
            row["instance_id"] = f"b{assign_counter:06d}"
    next_bseq = max(saved_bseq, _max_building_instance_seq_from_rows(plot_buildings_m), assign_counter)
    plot_stock: dict[str, dict[str, int]] = {}
    raw_stock = d.get("plot_output_stock") or {}
    for pk, inner in raw_stock.items():
        if not isinstance(inner, dict):
            continue
        plot_stock[str(pk)] = {str(m): int(q) for m, q in inner.items()}
    use_plot_logistics = bool(d.get("use_plot_output_logistics", False))
    reg_keys = d.get("market_seller_registered") or []
    seller_reg: set[str] = {str(x) for x in reg_keys} if isinstance(reg_keys, list) else set()
    world = World(
        seed=seed,
        tick=int(d["tick"]),
        plots=plots,
        ledger=ledger,
        inventory=inv,
        parties=parties,
        active_production=active,
        next_production_seq=int(d.get("next_production_seq", 0)),
        in_transit=transit,
        next_shipment_seq=int(d.get("next_shipment_seq", 0)),
        market_asks_by_material=asks_map,
        market_bids_by_material=bids_map,
        next_order_seq=int(d.get("next_order_seq", 0)),
        reputation=copy.deepcopy(dict(d.get("reputation", {}))),
        contracts=[copy.deepcopy(c) for c in d.get("contracts", [])],
        next_contract_seq=int(d.get("next_contract_seq", 0)),
        event_log=[copy.deepcopy(e) for e in d.get("event_log", [])],
        world_feed_log=[copy.deepcopy(e) for e in d.get("world_feed_log", [])],
        plot_buildings=plot_buildings_m,
        stub_hires=[copy.deepcopy(h) for h in d.get("stub_hires", [])],
        market_history=[copy.deepcopy(h) for h in d.get("market_history", [])],
        p2p_idempotency={str(k): copy.deepcopy(v) for k, v in d.get("p2p_idempotency", {}).items()},
        scenario_id=str(d.get("scenario_id", "frontier")),
        world_id=str(d.get("world_id", "")),
        world_name=str(d.get("world_name", "")),
        market_intel_expires_tick=int(d.get("market_intel_expires_tick", 0)),
        next_building_instance_seq=next_bseq,
        llm_agents=copy.deepcopy(dict(d.get("llm_agents", {}))),
        npc_messages_to_player=[
            copy.deepcopy(x) for x in d.get("npc_messages_to_player", d.get("npc_messages", []))
        ],
        llm_session_cost_micro_usd=int(d.get("llm_session_cost_micro_usd", 0)),
        llm_session_input_tokens=int(d.get("llm_session_input_tokens", 0)),
        llm_session_output_tokens=int(d.get("llm_session_output_tokens", 0)),
        deployed_lua_sources=copy.deepcopy(dict(d.get("deployed_lua_sources", {}))),
        party_display_names=copy.deepcopy(dict(d.get("party_display_names", {}))),
        scenario_state=_scenario_state_for_snapshot(dict(d.get("scenario_state", {}))),
        use_plot_output_logistics=use_plot_logistics,
        plot_output_stock=plot_stock,
        market_seller_registered=seller_reg,
    )
    # Restore (or seed) per-party recipe books — older snapshots predate this field, so we
    # ensure every known party has at least the Tier-1 starter set so production isn't blocked.
    from realm.world import ensure_party_recipe_book

    raw_books = d.get("party_recipe_books") or {}
    if isinstance(raw_books, dict):
        for k, v in raw_books.items():
            if isinstance(v, (list, set, tuple)):
                world.party_recipe_books[str(k)] = {str(x) for x in v}
    for px in world.parties:
        ensure_party_recipe_book(world, px)
    from realm.production.blueprints import Blueprint, seed_world_blueprints
    from realm.world.placed_buildings import PlacedBuilding, sync_plot_buildings_from_placed
    from realm.world.world import SubPlot

    seed_world_blueprints(world)
    for bid, raw in (d.get("blueprints") or {}).items():
        if isinstance(raw, dict) and bid not in world.blueprints:
            world.blueprints[str(bid)] = Blueprint(
                blueprint_id=str(bid),
                name=str(raw.get("name", bid)),
                description=str(raw.get("description", "")),
                footprint_w=int(raw.get("footprint_w", 3)),
                footprint_h=int(raw.get("footprint_h", 3)),
                construction_materials=dict(raw.get("construction_materials") or {}),
                construction_labor_cents=int(raw.get("construction_labor_cents", 0)),
                construction_ticks=int(raw.get("construction_ticks", 0)),
                enabled_recipe_ids=list(raw.get("enabled_recipe_ids") or []),
                maintenance_interval_ticks=int(raw.get("maintenance_interval_ticks", 0)),
                maintenance_materials=dict(raw.get("maintenance_materials") or {}),
                maintenance_grace_ticks=int(raw.get("maintenance_grace_ticks", 0)),
                is_seeded=bool(raw.get("is_seeded", False)),
                creator_party=raw.get("creator_party"),
                is_public=bool(raw.get("is_public", True)),
                license_fee_cents=int(raw.get("license_fee_cents", 0)),
                license_contract_id=raw.get("license_contract_id"),
                category=str(raw.get("category", "custom")),
                terrain_requirements=list(raw.get("terrain_requirements") or []),
                requires_coastal=bool(raw.get("requires_coastal", False)),
                requires_power=bool(raw.get("requires_power", False)),
            )
    for iid, raw in (d.get("placed_buildings") or {}).items():
        if not isinstance(raw, dict):
            continue
        world.placed_buildings[str(iid)] = PlacedBuilding(
            instance_id=str(raw.get("instance_id", iid)),
            blueprint_id=str(raw.get("blueprint_id", raw.get("building_id", ""))),
            plot_id=str(raw.get("plot_id", "")),
            grid_x=int(raw.get("grid_x", 0)),
            grid_y=int(raw.get("grid_y", 0)),
            built_at_tick=int(raw.get("built_at_tick", raw.get("completes_at_tick", 0))),
            built_by=str(raw.get("built_by", raw.get("party", ""))),
            status=str(raw.get("status", "active")),
            efficiency_pct=int(raw.get("efficiency_pct", 100)),
            missed_maintenance_cycles=int(raw.get("missed_maintenance_cycles", 0)),
            due_at_tick=int(raw.get("due_at_tick", 0)),
            sub_plot_id=raw.get("sub_plot_id"),
            original_cost_cents=int(raw.get("original_cost_cents", 0)),
            book_value_cents=int(raw.get("book_value_cents", 0)),
            depreciation_rate_per_year=float(
                raw.get("depreciation_rate_per_year", 0.05)
            ),
        )
    world.plot_placed_buildings = copy.deepcopy(
        dict(d.get("plot_placed_buildings") or {})
    )
    if world.placed_buildings:
        sync_plot_buildings_from_placed(world)
    gw = int(d.get("grid_width", 0))
    gh = int(d.get("grid_height", 0))
    if gw > 0 and gh > 0:
        world.scenario_state["grid_width"] = gw
        world.scenario_state["grid_height"] = gh
    elif not world.scenario_state.get("grid_width"):
        sw, sh = _snapshot_grid_size(saved_plots)
        world.scenario_state["grid_width"] = sw
        world.scenario_state["grid_height"] = sh
    for sid, raw in (d.get("sub_plots") or {}).items():
        if not isinstance(raw, dict):
            continue
        world.sub_plots[str(sid)] = SubPlot(
            sub_plot_id=str(raw.get("sub_plot_id", sid)),
            parent_plot_id=str(raw.get("parent_plot_id", "")),
            owner=raw.get("owner"),
            grid_x=int(raw.get("grid_x", 0)),
            grid_y=int(raw.get("grid_y", 0)),
            grid_w=int(raw.get("grid_w", 2)),
            grid_h=int(raw.get("grid_h", 2)),
            area_sq_metres=int(raw.get("area_sq_metres", 0)),
            listed_for_sale=bool(raw.get("listed_for_sale", False)),
            ask_price_cents=int(raw.get("ask_price_cents", 0)),
            lease_rights=copy.deepcopy(raw.get("lease_rights")),
        )
    raw_maint = d.get("building_maintenance") or {}
    if isinstance(raw_maint, dict):
        for k, v in raw_maint.items():
            if isinstance(v, dict):
                world.building_maintenance[str(k)] = {
                    str(kk): int(vv) for kk, vv in v.items()
                }
    raw_reports = d.get("survey_reports") or {}
    if isinstance(raw_reports, dict):
        for rid, payload in raw_reports.items():
            if not isinstance(payload, dict):
                continue
            world.survey_reports[str(rid)] = SurveyReport(
                report_id=str(payload.get("report_id", rid)),
                plot_id=PlotId(str(payload.get("plot_id", ""))),
                conducted_by=PartyId(str(payload.get("conducted_by", ""))),
                conducted_at_tick=int(payload.get("conducted_at_tick", 0)),
                grades={
                    str(k): float(v) for k, v in (payload.get("grades") or {}).items()
                },
                survey_type=str(payload.get("survey_type", "standard")),
                is_deep=bool(payload.get("is_deep", False)),
            )
    world.next_report_seq = int(d.get("next_report_seq", 0))
    world.intel_listings = [copy.deepcopy(row) for row in d.get("intel_listings", []) or []]
    world.next_intel_listing_seq = int(d.get("next_intel_listing_seq", 0))
    world.plot_listings = [copy.deepcopy(row) for row in d.get("plot_listings", []) or []]
    world.next_plot_listing_seq = int(d.get("next_plot_listing_seq", 0))
    world.survey_authorizations = [
        copy.deepcopy(row) for row in d.get("survey_authorizations", []) or []
    ]
    world.liens = [copy.deepcopy(row) for row in d.get("liens", []) or []]
    world.next_lien_seq = int(d.get("next_lien_seq", 0))
    world.analytics_purchases = [
        copy.deepcopy(row) for row in d.get("analytics_purchases", []) or []
    ]
    raw_biz = d.get("business_registry") or {}
    if isinstance(raw_biz, dict):
        for pid_s, payload in raw_biz.items():
            if not isinstance(payload, dict):
                continue
            world.business_registry[str(pid_s)] = BusinessRecord(
                party_id=PartyId(str(payload.get("party_id", pid_s))),
                business_name=str(payload.get("business_name", "")),
                description=str(payload.get("description", "")),
                registered_at_tick=int(payload.get("registered_at_tick", 0)),
            )
    raw_roads = d.get("road_segments") or []
    if isinstance(raw_roads, list):
        for payload in raw_roads:
            if not isinstance(payload, dict):
                continue
            world.road_segments.append(
                RoadSegment(
                    segment_id=str(payload.get("segment_id", "")),
                    from_plot=PlotId(str(payload.get("from_plot", ""))),
                    to_plot=PlotId(str(payload.get("to_plot", ""))),
                    owner=PartyId(str(payload.get("owner", ""))),
                    built_at_tick=int(payload.get("built_at_tick", 0)),
                    toll_rate_pct=int(payload.get("toll_rate_pct", 0)),
                    condition_bps=int(payload.get("condition_bps", 10_000)),
                    last_maintenance_tick=int(payload.get("last_maintenance_tick", 0)),
                )
            )
    world.next_road_segment_seq = int(d.get("next_road_segment_seq", 0))
    raw_jobs = d.get("job_openings") or []
    if isinstance(raw_jobs, list):
        from realm.population.employment import JobOpening

        for payload in raw_jobs:
            if not isinstance(payload, dict):
                continue
            world.job_openings.append(
                JobOpening(
                    opening_id=str(payload.get("opening_id", "")),
                    employer=PartyId(str(payload.get("employer", ""))),
                    plot_id=PlotId(str(payload.get("plot_id", ""))),
                    skill_min=int(payload.get("skill_min", 0)),
                    wage_per_day_cents=int(payload.get("wage_per_day_cents", 0)),
                    posted_at_tick=int(payload.get("posted_at_tick", 0)),
                    filled_by=(
                        str(payload["filled_by"]) if payload.get("filled_by") else None
                    ),
                    cpi_indexed=bool(payload.get("cpi_indexed", False)),
                )
            )
    world.next_business_seq = int(d.get("next_business_seq", 0))
    raw_biz = d.get("business_entities") or []
    if isinstance(raw_biz, list):
        from realm.economy.businesses import BusinessEntity

        for payload in raw_biz:
            if not isinstance(payload, dict):
                continue
            bid = str(payload.get("business_id", ""))
            if not bid:
                continue
            plots_raw = payload.get("registered_plot_ids") or []
            world.businesses[bid] = BusinessEntity(
                business_id=bid,
                owner_party=PartyId(str(payload.get("owner_party", ""))),
                business_name=str(payload.get("business_name", "")),
                business_type_tag=str(payload.get("business_type_tag", "")),
                description=str(payload.get("description", "")),
                registered_at_tick=int(payload.get("registered_at_tick", 0)),
                registered_plot_ids=tuple(PlotId(str(p)) for p in plots_raw),
                sub_account_label=str(payload.get("sub_account_label", "main")),
                status=str(payload.get("status", "active")),
                suspension_reason=(
                    str(payload["suspension_reason"])
                    if payload.get("suspension_reason")
                    else None
                ),
                public_profile=bool(payload.get("public_profile", True)),
                last_viability_check_tick=int(payload.get("last_viability_check_tick", 0)),
                equity_contract_ids=[str(x) for x in (payload.get("equity_contract_ids") or [])],
            )
    world.next_nascent_settlement_seq = int(d.get("next_nascent_settlement_seq", 0))
    raw_ns = d.get("nascent_settlements") or []
    if isinstance(raw_ns, list):
        from realm.population.nascent_settlements import NascentSettlement

        for payload in raw_ns:
            if not isinstance(payload, dict):
                continue
            nid = str(payload.get("nascent_id", ""))
            if not nid:
                continue
            mem = payload.get("member_plot_ids") or []
            world.nascent_settlements[nid] = NascentSettlement(
                nascent_id=nid,
                island_id=int(payload.get("island_id", 0)),
                anchor_plot_id=PlotId(str(payload.get("anchor_plot_id", ""))),
                member_plot_ids=tuple(PlotId(str(p)) for p in mem),
                resident_count=int(payload.get("resident_count", 0)),
                consecutive_game_days=int(payload.get("consecutive_game_days", 0)),
                last_checked_tick=int(payload.get("last_checked_tick", 0)),
            )
    for store_field in ("store_inventories", "store_prices"):
        raw_store = d.get(store_field) or {}
        if isinstance(raw_store, dict):
            target = getattr(world, store_field)
            for pid, inner in raw_store.items():
                if not isinstance(inner, dict):
                    continue
                target[str(pid)] = {str(k): int(v) for k, v in inner.items()}
    raw_rev = d.get("store_revenue_today") or {}
    if isinstance(raw_rev, dict):
        for pid, c in raw_rev.items():
            world.store_revenue_today[str(pid)] = int(c)
    raw_towns = d.get("towns") or {}
    if isinstance(raw_towns, dict):
        from realm.population.towns import Town

        for tid, payload in raw_towns.items():
            if not isinstance(payload, dict):
                continue
            world.towns[str(tid)] = Town(
                town_id=str(payload.get("town_id", tid)),
                name=str(payload.get("name", "")),
                island_id=int(payload.get("island_id", 0)),
                center_plot=PlotId(str(payload.get("center_plot", ""))),
                residential_plots=[
                    PlotId(str(p)) for p in (payload.get("residential_plots") or [])
                ],
                laborer_count=int(payload.get("laborer_count", 0)),
                store_plots=[
                    PlotId(str(p)) for p in (payload.get("store_plots") or [])
                ],
            )
    raw_laborers = d.get("laborers") or {}
    if isinstance(raw_laborers, dict):
        from realm.population.laborers import LaborerNPC

        for lid, payload in raw_laborers.items():
            if not isinstance(payload, dict):
                continue
            employer_raw = payload.get("employer")
            world.laborers[str(lid)] = LaborerNPC(
                laborer_id=str(payload.get("laborer_id", lid)),
                display_name=str(payload.get("display_name", "")),
                island_id=int(payload.get("island_id", 0)),
                home_plot_id=PlotId(str(payload.get("home_plot_id", ""))),
                home_town=(
                    str(payload["home_town"]) if payload.get("home_town") else None
                ),
                employer=PartyId(str(employer_raw)) if employer_raw else None,
                skill_level=int(payload.get("skill_level", 0)),
                age_ticks=int(payload.get("age_ticks", 0)),
                health=float(payload.get("health", 1.0)),
                cash_cents=int(payload.get("cash_cents", 0)),
                needs={
                    str(k): float(v)
                    for k, v in (payload.get("needs") or {}).items()
                },
                employment_contract=(
                    str(payload["employment_contract"])
                    if payload.get("employment_contract")
                    else None
                ),
                wage_per_day_cents=int(payload.get("wage_per_day_cents", 0)),
                migrating_to=(
                    str(payload["migrating_to"]) if payload.get("migrating_to") else None
                ),
                migration_arrives_tick=int(payload.get("migration_arrives_tick", 0)),
                last_needs_tick=int(payload.get("last_needs_tick", 0)),
            )
    raw_fu = d.get("futures_orders") or []
    if isinstance(raw_fu, list):
        from realm.economy.futures import FuturesOrder

        for row in raw_fu:
            if not isinstance(row, dict):
                continue
            oid = str(row.get("order_id", ""))
            if not oid:
                continue
            world.futures_orders.append(
                FuturesOrder(
                    order_id=oid,
                    side=str(row.get("side", "")),
                    poster=PartyId(str(row.get("poster", ""))),
                    material=MaterialId(str(row.get("material", ""))),
                    qty=int(row.get("qty", 0)),
                    price_per_unit_cents=int(row.get("price_per_unit_cents", 0)),
                    delivery_tick=int(row.get("delivery_tick", 0)),
                    deposit_cents=int(row.get("deposit_cents", 0)),
                    status=str(row.get("status", "open")),
                    matched_with=(
                        str(row["matched_with"]) if row.get("matched_with") else None
                    ),
                    posted_at_tick=int(row.get("posted_at_tick", 0)),
                    match_price_cents=(
                        int(row["match_price_cents"])
                        if row.get("match_price_cents") is not None
                        else None
                    ),
                )
            )
    raw_fx = d.get("fx_orders") or []
    if isinstance(raw_fx, list):
        from realm.economy.fx_market import FXOrder

        for row in raw_fx:
            if not isinstance(row, dict):
                continue
            oid = str(row.get("order_id", ""))
            if not oid:
                continue
            world.fx_orders.append(
                FXOrder(
                    order_id=oid,
                    poster=PartyId(str(row.get("poster", ""))),
                    sell_material=str(row.get("sell_material", "")),
                    sell_qty=int(row.get("sell_qty", 0)),
                    buy_material=str(row.get("buy_material", "")),
                    buy_qty_min=int(row.get("buy_qty_min", 0)),
                    posted_at_tick=int(row.get("posted_at_tick", 0)),
                    status=str(row.get("status", "open")),
                    expires_at_tick=int(row.get("expires_at_tick", 0)),
                    filled_sell_qty=int(row.get("filled_sell_qty", 0)),
                    filled_buy_qty=int(row.get("filled_buy_qty", 0)),
                )
            )
    raw_ic = d.get("issued_currencies") or {}
    if isinstance(raw_ic, dict):
        from realm.economy.currencies import IssuedCurrency
        from realm.materials import register_currency_material

        for cid, payload in raw_ic.items():
            if not isinstance(payload, dict):
                continue
            ic = IssuedCurrency(
                currency_id=str(payload.get("currency_id", cid)),
                symbol=str(payload.get("symbol", "")),
                name=str(payload.get("name", "")),
                issuer_party=str(payload.get("issuer_party", "")),
                business_id=str(payload.get("business_id", "")),
                material_id=str(payload.get("material_id", "")),
                reserve_ratio=float(payload.get("reserve_ratio", 0.2)),
                total_issued=int(payload.get("total_issued", 0)),
                reserve_cents=int(payload.get("reserve_cents", 0)),
                created_at_tick=int(payload.get("created_at_tick", 0)),
                status=str(payload.get("status", "active")),
            )
            world.issued_currencies[str(cid)] = ic
            register_currency_material(MaterialId(ic.material_id), ic.name)
    raw_ra = d.get("regional_advantages") or {}
    if isinstance(raw_ra, dict):
        for lk_s, inner in raw_ra.items():
            if not isinstance(inner, dict):
                continue
            try:
                lk = int(lk_s)
            except (TypeError, ValueError):
                continue
            world.regional_advantages[lk] = {
                str(kk): float(vv) for kk, vv in inner.items()
            }
    # Sprint 6 — Phase D.1: matter no longer lives in ``plot_output_stock``.
    # Migrate any staged output from old snapshots (version ≤ 10) into the
    # plot owner's inventory and reset the per-plot dict to a fresh display log.
    if int(ver) <= 10:
        migrated = False
        for plot_id_s, mats in list(world.plot_output_stock.items()):
            plot = world.plots.get(PlotId(plot_id_s))
            if plot is None or plot.owner is None:
                continue
            for mat_s, qty in list(mats.items()):
                try:
                    q = int(qty)
                except (TypeError, ValueError):
                    continue
                if q <= 0:
                    continue
                world.inventory.add(plot.owner, MaterialId(str(mat_s)), q)
                migrated = True
        if migrated:
            # Display log starts fresh — old saves' counters are subsumed into inventory.
            world.plot_output_stock = {}
    if not str(world.world_id or "").strip():
        from realm.core.ids import new_world_id

        world.world_id = str(new_world_id())
    return world


def dumps_json(world: World) -> str:
    return json.dumps(dump_world(world), indent=2)


def loads_json(s: str) -> World:
    return load_world(json.loads(s))

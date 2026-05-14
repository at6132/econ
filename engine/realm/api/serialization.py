"""Serialize / deserialize full World for SQLite persistence.

Snapshot ``version`` is ``7`` (older rows still load). Nested dict/list values are deep-copied on dump
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
SNAPSHOT_VERSION = 12


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
    for pid, p in world.plots.items():
        plots_out[str(pid)] = {
            "x": p.x,
            "y": p.y,
            "terrain": p.terrain.value,
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
                "escrow_cents": b.escrow_cents,
                "iceberg_peak": b.iceberg_peak,
                "iceberg_hidden_qty": b.iceberg_hidden_qty,
                "min_counterparty_honored": b.min_counterparty_honored,
            }
            for b in lst
        ]
    inv: dict[str, dict[str, int]] = {}
    for party in sorted(world.inventory.parties_with_stock_rows(), key=str):
        mats = world.inventory.stock_for_party(party)
        inv[str(party)] = {str(m): q for m, q in mats.items()}
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
        "stub_hires": [copy.deepcopy(h) for h in world.stub_hires],
        "market_history": [copy.deepcopy(h) for h in world.market_history],
        "p2p_idempotency": {str(k): copy.deepcopy(dict(v)) for k, v in world.p2p_idempotency.items()},
        "scenario_id": world.scenario_id,
        "market_intel_expires_tick": world.market_intel_expires_tick,
        "next_building_instance_seq": world.next_building_instance_seq,
        "llm_agents": copy.deepcopy(dict(world.llm_agents)),
        "npc_messages_to_player": copy.deepcopy(list(world.npc_messages_to_player)),
        "llm_session_cost_micro_usd": world.llm_session_cost_micro_usd,
        "llm_session_input_tokens": world.llm_session_input_tokens,
        "llm_session_output_tokens": world.llm_session_output_tokens,
        "deployed_lua_sources": copy.deepcopy(dict(world.deployed_lua_sources)),
        "party_display_names": copy.deepcopy(dict(world.party_display_names)),
        "scenario_state": copy.deepcopy(dict(world.scenario_state)),
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
            }
            for op in world.job_openings
        ],
    }


def load_world(d: dict[str, Any]) -> World:
    ver = d.get("version", 1)
    if ver not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12):
        raise ValueError(f"unsupported snapshot version: {ver!r}")
    seed = int(d["seed"])
    width = max(int(p["x"]) for p in d["plots"].values()) + 1
    height = max(int(p["y"]) for p in d["plots"].values()) + 1
    plots = generate_plots(seed=seed, width=width, height=height)
    for pid_str, saved in d["plots"].items():
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
                iceberg_peak=int(r.get("iceberg_peak", 0)),
                iceberg_hidden_qty=int(r.get("iceberg_hidden_qty", 0)),
                min_counterparty_honored=int(r.get("min_counterparty_honored", 0)),
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
        scenario_state=copy.deepcopy(dict(d.get("scenario_state", {}))),
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
                )
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
                migrating_to=(
                    str(payload["migrating_to"]) if payload.get("migrating_to") else None
                ),
                migration_arrives_tick=int(payload.get("migration_arrives_tick", 0)),
                last_needs_tick=int(payload.get("last_needs_tick", 0)),
            )
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
    return world


def dumps_json(world: World) -> str:
    return json.dumps(dump_world(world), indent=2)


def loads_json(s: str) -> World:
    return load_world(json.loads(s))

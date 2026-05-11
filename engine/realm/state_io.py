"""Serialize / deserialize full World for SQLite persistence.

Snapshot ``version`` is ``4`` (older rows still load). Nested dict/list values are deep-copied on dump
so JSON round-trips do not share mutable subgraphs with the live ``World``.

``load_world`` uses defaults via ``dict.get`` so older SQLite/JSON rows remain loadable when new
fields are additive (e.g. ``market_bids``, ``best_bids_cents`` in history).
"""

from __future__ import annotations

import copy
import json
from typing import Any

from realm.decay import BUILDING_CONDITION_FULL_BPS
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import Inventory
from realm.ledger import Ledger
from realm.markets import AskOrder, BidOrder
from realm.world import (
    ActiveProduction,
    InTransit,
    SubsurfaceRoll,
    World,
    generate_plots,
)
from realm.terrain import Terrain

# Bump when serialized shape or semantics change; loaders accept older versions they understand.
SNAPSHOT_VERSION = 4


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
            "subsurface": {
                "iron_ore_grade": p.subsurface.iron_ore_grade,
                "copper_ore_grade": p.subsurface.copper_ore_grade,
                "clay_grade": p.subsurface.clay_grade,
                "coal_grade": p.subsurface.coal_grade,
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
            }
            for s in world.in_transit
        ],
        "market_asks": asks,
        "market_bids": bids,
        "reputation": copy.deepcopy(dict(world.reputation)),
        "contracts": [copy.deepcopy(c) for c in world.contracts],
        "event_log": [copy.deepcopy(e) for e in world.event_log],
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
    }


def load_world(d: dict[str, Any]) -> World:
    ver = d.get("version", 1)
    if ver not in (1, 2, 3, 4):
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
        sub = saved.get("subsurface") or {}
        p.subsurface = SubsurfaceRoll(
            iron_ore_grade=float(sub.get("iron_ore_grade", 0)),
            copper_ore_grade=float(sub.get("copper_ore_grade", 0)),
            clay_grade=float(sub.get("clay_grade", 0)),
            coal_grade=float(sub.get("coal_grade", 0)),
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
    )
    return world


def dumps_json(world: World) -> str:
    return json.dumps(dump_world(world), indent=2)


def loads_json(s: str) -> World:
    return load_world(json.loads(s))

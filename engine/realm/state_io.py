"""Serialize / deserialize full World for SQLite persistence."""

from __future__ import annotations

import json
from typing import Any

from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import Inventory
from realm.ledger import Ledger
from realm.markets import AskOrder
from realm.world import (
    ActiveProduction,
    InTransit,
    SubsurfaceRoll,
    World,
    generate_plots,
)
from realm.terrain import Terrain


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
            }
            for o in lst
        ]
    inv: dict[str, dict[str, int]] = {}
    for party, mats in world.inventory.snapshot().items():
        inv[str(party)] = {str(m): q for m, q in mats.items()}
    return {
        "version": 1,
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
            }
            for s in world.in_transit
        ],
        "market_asks": asks,
        "reputation": dict(world.reputation),
        "contracts": list(world.contracts),
        "event_log": list(world.event_log),
        "plot_buildings": list(world.plot_buildings),
        "stub_hires": list(world.stub_hires),
    }


def load_world(d: dict[str, Any]) -> World:
    if d.get("version") != 1:
        raise ValueError("unsupported snapshot version")
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
            )
            for r in rows
        ]
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
        next_order_seq=int(d.get("next_order_seq", 0)),
        reputation=dict(d.get("reputation", {})),
        contracts=list(d.get("contracts", [])),
        next_contract_seq=int(d.get("next_contract_seq", 0)),
        event_log=list(d.get("event_log", [])),
        plot_buildings=list(d.get("plot_buildings", [])),
        stub_hires=list(d.get("stub_hires", [])),
    )
    return world


def dumps_json(world: World) -> str:
    return json.dumps(dump_world(world), indent=2)


def loads_json(s: str) -> World:
    return load_world(json.loads(s))

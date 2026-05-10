"""Thin FastAPI layer — clients propose; engine validates (Law 10)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from realm.actions import claim_plot, hire_catalog_public, hire_worker_stub, start_production_on_plot, survey_plot
from realm.buildings import build_on_plot
from realm.ids import MaterialId, PartyId, PlotId
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
from realm.social import honor_contract_stub, propose_contract_stub
from realm.tick import advance_tick
from realm.world import bootstrap_frontier, world_public_dict

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


@app.get("/world")
def get_world() -> dict:
    return world_public_dict(_world)


@app.get("/hire/catalog")
def get_hire_catalog() -> dict:
    return {"roles": hire_catalog_public()}


@app.post("/tick")
def post_tick() -> dict:
    advance_tick(_world)
    return {"ok": True, "tick": _world.tick}


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
    return dict(r)


@app.post("/plots/{plot_id}/survey")
def post_survey(plot_id: str, party: Annotated[str, Query()] = "player") -> dict:
    r = survey_plot(_world, PartyId(party), PlotId(plot_id))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/plots/{plot_id}/build")
def post_build(
    plot_id: str,
    building_id: Annotated[str, Query()],
    party: Annotated[str, Query()] = "player",
) -> dict:
    r = build_on_plot(_world, PartyId(party), PlotId(plot_id), building_id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/hire")
def post_hire(
    employer: Annotated[str, Query()],
    employee: Annotated[str, Query()],
    signing_bonus_cents: Annotated[int, Query()],
) -> dict:
    r = hire_worker_stub(_world, PartyId(employer), PartyId(employee), signing_bonus_cents)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/dev/reset")
def dev_reset(seed: Annotated[int, Query()] = 42) -> dict:
    """Recreate Frontier world (dev only)."""
    global _world
    _world = bootstrap_frontier(seed=seed)
    return {"ok": True, "seed": seed}


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


@app.post("/market/sell")
def post_market_sell(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    price_per_unit_cents: Annotated[int, Query()],
) -> dict:
    r = place_sell_order(_world, PartyId(party), MaterialId(material), qty, price_per_unit_cents)
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
) -> dict:
    r = place_buy_order(
        _world,
        PartyId(party),
        MaterialId(material),
        qty,
        max_price_per_unit_cents,
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
) -> dict:
    r = sell_into_bids(_world, PartyId(party), MaterialId(material), max_qty)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/market/buy")
def post_market_buy(
    party: Annotated[str, Query()],
    material: Annotated[str, Query()],
    max_qty: Annotated[int, Query()],
) -> dict:
    r = market_buy(_world, PartyId(party), MaterialId(material), max_qty)
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
) -> dict:
    r = p2p_trade(
        _world,
        PartyId(seller),
        PartyId(buyer),
        MaterialId(material),
        qty,
        total_price_cents,
    )
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

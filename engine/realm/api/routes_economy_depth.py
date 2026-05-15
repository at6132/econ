"""API routes: CPI, futures, FX, and player-bank currencies (read + post/cancel)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from realm.actions.depth_markets_actions import (
    cancel_futures_order_action,
    cancel_fx_order_action,
    create_currency_action,
    mint_currency_action,
    post_fx_order_action,
    post_futures_order_action,
    redeem_currency_action,
)
from realm.api import _state
from realm.core.ids import PartyId
from realm.economy.cpi import CPI_BASKET

router = APIRouter(tags=["economy-depth"])


def _party(pid: str) -> PartyId:
    return PartyId(str(pid))


@router.get("/economy/cpi")
def get_cpi() -> dict[str, Any]:
    w = _state.WORLD
    return {
        "current": float(w.scenario_state.get("cpi_current", 100.0)),
        "history": list(w.scenario_state.get("cpi_history") or []),
    }


@router.get("/economy/cpi/components")
def get_cpi_components() -> dict[str, Any]:
    w = _state.WORLD
    hist = list(w.scenario_state.get("cpi_history") or [])
    last = hist[-1] if hist else {}
    comp = last.get("component_prices") if isinstance(last, dict) else {}
    if not isinstance(comp, dict):
        comp = {}
    basket = {m: float(wt) for m, wt in CPI_BASKET.items()}
    return {
        "tick": int(last.get("tick", w.tick)) if isinstance(last, dict) else int(w.tick),
        "cpi": float(last.get("cpi", w.scenario_state.get("cpi_current", 100.0)))
        if isinstance(last, dict)
        else float(w.scenario_state.get("cpi_current", 100.0)),
        "component_prices": {str(k): int(v) for k, v in comp.items()},
        "basket_weights": basket,
    }


@router.post("/futures/orders")
def post_futures_order_route(
    party: Annotated[str, Query()],
    side: Annotated[str, Query()],
    material: Annotated[str, Query()],
    qty: Annotated[int, Query()],
    price_per_unit_cents: Annotated[int, Query()],
    delivery_tick: Annotated[int, Query()],
) -> dict[str, Any]:
    r = post_futures_order_action(
        _state.WORLD,
        _party(party),
        side,
        material,
        qty,
        price_per_unit_cents,
        delivery_tick,
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.delete("/futures/orders/{order_id}")
def delete_futures_order_route(
    order_id: str,
    party: Annotated[str, Query()],
) -> dict[str, Any]:
    r = cancel_futures_order_action(_state.WORLD, _party(party), order_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/futures/orders")
def list_futures_orders(
    material: Annotated[str | None, Query()] = None,
    delivery_tick: Annotated[int | None, Query()] = None,
    status: Annotated[str, Query()] = "open",
) -> dict[str, Any]:
    w = _state.WORLD
    out: list[Any] = []
    for o in w.futures_orders:
        if str(o.status) != str(status):
            continue
        if material is not None and str(o.material) != str(material):
            continue
        if delivery_tick is not None and int(o.delivery_tick) != int(delivery_tick):
            continue
        out.append(
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
        )
    return {"orders": out}


@router.get("/futures/curve/{material}")
def futures_curve(material: str) -> dict[str, Any]:
    w = _state.WORLD
    mat = str(material)
    rows: list[dict[str, Any]] = []
    for o in w.futures_orders:
        if str(o.material) != mat or o.status != "matched" or o.side != "sell":
            continue
        px = int(o.match_price_cents or o.price_per_unit_cents)
        rows.append({"delivery_tick": int(o.delivery_tick), "price_cents": px})
    rows.sort(key=lambda r: r["delivery_tick"])
    return {"material": mat, "points": rows}


@router.get("/futures/mine")
def futures_mine(party: Annotated[str, Query()] = "player") -> dict[str, Any]:
    w = _state.WORLD
    pid = _party(party)
    mine: list[Any] = []
    for o in w.futures_orders:
        if o.poster != pid:
            continue
        if str(o.status) not in ("open", "matched"):
            continue
        mine.append(
            {
                "order_id": o.order_id,
                "side": o.side,
                "material": str(o.material),
                "qty": int(o.qty),
                "price_per_unit_cents": int(o.price_per_unit_cents),
                "delivery_tick": int(o.delivery_tick),
                "status": str(o.status),
                "matched_with": o.matched_with,
            }
        )
    return {"party": str(pid), "orders": mine}


@router.post("/banks/currency/create")
def banks_currency_create(
    party: Annotated[str, Query()],
    business_id: Annotated[str, Query()],
    symbol: Annotated[str, Query()],
    name: Annotated[str, Query()],
    reserve_ratio: Annotated[float, Query()] = 0.20,
) -> dict[str, Any]:
    r = create_currency_action(
        _state.WORLD, _party(party), business_id, symbol, name, reserve_ratio
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/banks/currency/{currency_id}/mint")
def banks_currency_mint(
    currency_id: str,
    party: Annotated[str, Query()],
    amount: Annotated[int, Query()],
) -> dict[str, Any]:
    r = mint_currency_action(_state.WORLD, _party(party), currency_id, amount)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.post("/banks/currency/{currency_id}/redeem")
def banks_currency_redeem(
    currency_id: str,
    party: Annotated[str, Query()],
    amount: Annotated[int, Query()],
) -> dict[str, Any]:
    r = redeem_currency_action(_state.WORLD, _party(party), currency_id, amount)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/banks/currencies")
def banks_currencies_list() -> dict[str, Any]:
    w = _state.WORLD
    out = []
    for c in w.issued_currencies.values():
        ratio = (
            float(c.reserve_cents) / float(c.total_issued) if int(c.total_issued) > 0 else 0.0
        )
        out.append(
            {
                "currency_id": c.currency_id,
                "symbol": c.symbol,
                "name": c.name,
                "issuer_party": c.issuer_party,
                "business_id": c.business_id,
                "material_id": c.material_id,
                "reserve_ratio": float(c.reserve_ratio),
                "total_issued": int(c.total_issued),
                "reserve_cents": int(c.reserve_cents),
                "backing_ratio": ratio,
                "status": str(c.status),
            }
        )
    return {"currencies": out}


@router.get("/banks/currency/{currency_id}")
def banks_currency_detail(currency_id: str) -> dict[str, Any]:
    w = _state.WORLD
    c = w.issued_currencies.get(currency_id)
    if c is None:
        raise HTTPException(status_code=404, detail="unknown currency")
    ratio = float(c.reserve_cents) / float(c.total_issued) if int(c.total_issued) > 0 else 0.0
    return {
        "currency_id": c.currency_id,
        "symbol": c.symbol,
        "name": c.name,
        "issuer_party": c.issuer_party,
        "business_id": c.business_id,
        "material_id": c.material_id,
        "reserve_ratio": float(c.reserve_ratio),
        "total_issued": int(c.total_issued),
        "reserve_cents": int(c.reserve_cents),
        "backing_ratio": ratio,
        "status": str(c.status),
    }


@router.get("/banks/currency/{currency_id}/supply")
def banks_currency_supply(currency_id: str) -> dict[str, Any]:
    w = _state.WORLD
    c = w.issued_currencies.get(currency_id)
    if c is None:
        raise HTTPException(status_code=404, detail="unknown currency")
    te = (
        float(c.reserve_cents) / float(c.total_issued) if int(c.total_issued) > 0 else 0.0
    )
    return {
        "total_issued": int(c.total_issued),
        "reserve_cents": int(c.reserve_cents),
        "effective_exchange_rate_cents_per_unit": te,
    }


@router.post("/fx/orders")
def post_fx_order_route(
    party: Annotated[str, Query()],
    sell_material: Annotated[str, Query()],
    sell_qty: Annotated[int, Query()],
    buy_material: Annotated[str, Query()],
    buy_qty_min: Annotated[int, Query()],
) -> dict[str, Any]:
    r = post_fx_order_action(
        _state.WORLD,
        _party(party),
        sell_material,
        sell_qty,
        buy_material,
        buy_qty_min,
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.delete("/fx/orders/{order_id}")
def delete_fx_order_route(
    order_id: str,
    party: Annotated[str, Query()],
) -> dict[str, Any]:
    r = cancel_fx_order_action(_state.WORLD, _party(party), order_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("reason", "error")))
    return dict(r)


@router.get("/fx/orders")
def list_fx_orders(
    sell_material: Annotated[str | None, Query()] = None,
    buy_material: Annotated[str | None, Query()] = None,
    status: Annotated[str, Query()] = "open",
) -> dict[str, Any]:
    w = _state.WORLD
    out: list[Any] = []
    for o in w.fx_orders:
        if str(o.status) != str(status):
            continue
        if sell_material is not None and o.sell_material != str(sell_material):
            continue
        if buy_material is not None and o.buy_material != str(buy_material):
            continue
        out.append(
            {
                "order_id": o.order_id,
                "poster": str(o.poster),
                "sell_material": o.sell_material,
                "sell_qty": int(o.sell_qty),
                "buy_material": o.buy_material,
                "buy_qty_min": int(o.buy_qty_min),
                "posted_at_tick": int(o.posted_at_tick),
                "expires_at_tick": int(o.expires_at_tick),
                "status": str(o.status),
            }
        )
    return {"orders": out}


@router.get("/fx/rates")
def fx_rates() -> dict[str, Any]:
    w = _state.WORLD
    board = w.scenario_state.get("fx_rate_board") or {}
    if not isinstance(board, dict):
        return {"rates": {}}
    return {"rates": {str(k): float(v) for k, v in board.items()}}


@router.get("/fx/history/{pair}")
def fx_history(pair: str) -> dict[str, Any]:
    w = _state.WORLD
    hist = list(w.scenario_state.get("fx_rate_history") or [])
    key = str(pair).replace("-", "/")
    series: list[dict[str, Any]] = []
    for row in hist:
        if not isinstance(row, dict):
            continue
        board = row.get("board") or {}
        if not isinstance(board, dict):
            continue
        if key in board:
            series.append(
                {"tick": int(row.get("tick", 0)), "rate": float(board[key])}
            )
    return {"pair": key, "series": series}


@router.get("/fx/mine")
def fx_mine(party: Annotated[str, Query()] = "player") -> dict[str, Any]:
    w = _state.WORLD
    pid = _party(party)
    mine: list[Any] = []
    for o in w.fx_orders:
        if o.poster != pid:
            continue
        if str(o.status) not in ("open", "matched"):
            continue
        mine.append(
            {
                "order_id": o.order_id,
                "sell_material": o.sell_material,
                "sell_qty": int(o.sell_qty),
                "buy_material": o.buy_material,
                "buy_qty_min": int(o.buy_qty_min),
                "status": str(o.status),
            }
        )
    return {"party": str(pid), "orders": mine}

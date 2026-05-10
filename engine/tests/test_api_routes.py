"""Smoke FastAPI routes against the module singleton world (dev/reset between tests)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realm.api import app


def test_market_cancel_via_http_round_trip() -> None:
    c = TestClient(app)
    assert c.post("/dev/reset", params={"seed": 55}).status_code == 200
    r = c.post(
        "/market/sell",
        params={"party": "player", "material": "timber", "qty": 2, "price_per_unit_cents": 99},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    oid = body["order_id"]
    r2 = c.post("/market/cancel", params={"party": "player", "order_id": oid})
    assert r2.status_code == 200
    assert r2.json().get("ok") is True


def test_market_cancel_400_wrong_party() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 56})
    r = c.post(
        "/market/sell",
        params={"party": "player", "material": "timber", "qty": 1, "price_per_unit_cents": 10},
    )
    oid = r.json()["order_id"]
    r2 = c.post("/market/cancel", params={"party": "npc_grain_vendor", "order_id": oid})
    assert r2.status_code == 400


def test_p2p_trade_via_http() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 57})
    # Player has grain; consumer has cash from bootstrap — sell 1 grain P2P for 50¢ total
    r = c.post(
        "/trade/p2p",
        params={
            "seller": "player",
            "buyer": "t1_consumer",
            "material": "grain",
            "qty": 1,
            "total_price_cents": 50,
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True

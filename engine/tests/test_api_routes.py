"""Smoke FastAPI routes against the module singleton world (dev/reset between tests)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realm.api import app
from realm.decay import BUILDING_CONDITION_FULL_BPS


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


def test_supply_contract_http_flow() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 71})
    r = c.post(
        "/contracts/supply/propose",
        params={
            "supplier": "player",
            "buyer": "t1_consumer",
            "material": "grain",
            "qty": 1,
            "total_price_cents": 50,
            "due_in_ticks": 5,
        },
    )
    assert r.status_code == 200
    cid = r.json()["contract_id"]
    r2 = c.post("/contracts/supply/accept", params={"buyer": "t1_consumer", "contract_id": cid})
    assert r2.status_code == 200
    r3 = c.post("/contracts/supply/fulfill", params={"supplier": "player", "contract_id": cid})
    assert r3.status_code == 200


def test_market_bid_cancel_via_http() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 58})
    r = c.post(
        "/market/bid",
        params={
            "party": "t1_consumer",
            "material": "electricity",
            "qty": 1,
            "max_price_per_unit_cents": 100,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    oid = body["order_id"]
    r2 = c.post("/market/cancel_bid", params={"party": "t1_consumer", "order_id": oid})
    assert r2.status_code == 200
    assert r2.json().get("ok") is True


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


def test_p2p_http_error_returns_reason_and_code() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 59})
    r = c.post(
        "/trade/p2p",
        params={
            "seller": "player",
            "buyer": "t1_consumer",
            "material": "grain",
            "qty": 0,
            "total_price_cents": 50,
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "P2P_INVALID"
    assert "invalid" in body["detail"]["reason"].lower()


def test_p2p_http_idempotency_replay() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 60})
    params = {
        "seller": "player",
        "buyer": "t1_consumer",
        "material": "grain",
        "qty": 1,
        "total_price_cents": 50,
        "idempotency_key": "http-idem-1",
    }
    r1 = c.post("/trade/p2p", params=params)
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1.get("ok") is True
    r2 = c.post("/trade/p2p", params=params)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("idempotent_replay") is True


def test_survey_http_returns_terrain_and_recipe_ids() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 1})
    r = c.post("/plots/p-0-0/claim", params={"party": "player"})
    assert r.status_code == 200
    rb = c.post(
        "/plots/p-0-0/build",
        params={"building_id": "wood_shop", "party": "player", "build_mode": "turnkey"},
    )
    assert rb.status_code == 200
    r2 = c.post("/plots/p-0-0/survey", params={"party": "player"})
    assert r2.status_code == 200
    body = r2.json()
    assert body.get("ok") is True
    assert body.get("terrain") == "plains"
    assert isinstance(body.get("recipe_ids"), list)
    assert "sawmill" in body["recipe_ids"]
    assert len(body["recipe_ids"]) >= 3


def test_survey_http_conserves_ledger_total() -> None:
    import realm.api as api

    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 96})
    c.post("/plots/p-1-0/claim", params={"party": "player"})
    total_before = api._world.ledger.total_cents()
    r = c.post("/plots/p-1-0/survey", params={"party": "player"})
    assert r.status_code == 200
    assert api._world.ledger.total_cents() == total_before


def test_market_intel_http_conserves_ledger_total() -> None:
    import realm.api as api

    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 97})
    total_before = api._world.ledger.total_cents()
    r = c.post("/market/intel", params={"party": "player"})
    assert r.status_code == 200
    assert r.json().get("fee_cents") is not None
    assert api._world.ledger.total_cents() == total_before


def test_maintain_http_conserves_ledger_total() -> None:
    import realm.api as api

    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 98})
    c.post("/plots/p-0-0/claim", params={"party": "player"})
    c.post("/plots/p-0-0/survey", params={"party": "player"})
    rb = c.post("/plots/p-0-0/build", params={"party": "player", "building_id": "watch_hut"})
    assert rb.status_code == 200
    row = next(b for b in api._world.plot_buildings if b.get("building_id") == "watch_hut")
    row["condition_bps"] = 500
    total_before = api._world.ledger.total_cents()
    r = c.post(
        "/plots/p-0-0/maintain",
        params={"party": "player", "instance_id": str(row["instance_id"])},
    )
    assert r.status_code == 200
    assert api._world.ledger.total_cents() == total_before
    assert row["condition_bps"] == BUILDING_CONDITION_FULL_BPS

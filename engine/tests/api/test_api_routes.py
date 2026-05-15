"""Smoke FastAPI routes against the module singleton world (dev/reset between tests)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realm.api import app
from realm.production.decay import BUILDING_CONDITION_FULL_BPS
from realm.core.ids import PartyId

from turnkey_fixtures import grant_turnkey_self_materials


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


def test_tick_batch_advances_world() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 202})
    t0 = c.get("/world").json()["tick"]
    r = c.post("/tick/batch", params={"count": 100})
    assert r.status_code == 200
    b = r.json()
    assert b.get("ok") is True
    assert b.get("advanced") == 100
    assert b.get("tick_start") == t0
    assert b.get("tick") == t0 + 100


def test_tick_batch_400_when_count_over_cap() -> None:
    c = TestClient(app)
    r = c.post("/tick/batch", params={"count": 99_999})
    assert r.status_code == 400


def test_get_world_compact_shape() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 203})
    r = c.get("/world", params={"compact": 1})
    assert r.status_code == 200
    body = r.json()
    assert body.get("compact") is True
    assert "plots" not in body
    assert "player" in body
    assert "event_log_tail" in body


def test_tick_batch_includes_compact_summary_when_requested() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 204})
    r = c.post("/tick/batch", params={"count": 3, "summary": 1})
    assert r.status_code == 200
    b = r.json()
    assert b.get("ok") is True
    wc = b.get("world_compact")
    assert isinstance(wc, dict)
    assert wc.get("compact") is True


def test_produce_while_active_returns_200_with_started_false() -> None:
    c = TestClient(app)
    assert c.post("/dev/reset", params={"seed": 61}).status_code == 200
    pid = "p-0-0"
    assert c.post(f"/plots/{pid}/claim", params={"party": "player"}).status_code == 200
    assert c.post(f"/plots/{pid}/survey", params={"party": "player"}).status_code == 200
    import realm.api as api

    grant_turnkey_self_materials(api._world, PartyId("player"), "wood_shop")
    rb = c.post(
        f"/plots/{pid}/build",
        params={"party": "player", "building_id": "wood_shop", "build_mode": "turnkey"},
    )
    assert rb.status_code == 200, rb.text
    assert c.post("/tick/batch", params={"count": 180}).status_code == 200
    r1 = c.post(f"/plots/{pid}/produce", params={"party": "player", "recipe_id": "sawmill"})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1.get("ok") is True
    assert b1.get("started") is True
    assert isinstance(b1.get("completes_at_tick"), int)

    # Same tick: duplicate start should be a no-op with scheduling hints (HTTP 200).
    r2 = c.post(f"/plots/{pid}/produce", params={"party": "player", "recipe_id": "sawmill"})
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2.get("ok") is True
    assert b2.get("started") is False
    assert b2.get("status") == "active"
    assert b2.get("recipe_id") == "sawmill"
    assert b2.get("ticks_remaining") == b1.get("ticks_remaining")
    assert b2.get("completes_at_tick") == b1.get("completes_at_tick")
    assert "completes around tick" in (b2.get("message") or "")


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
    rs = c.post("/plots/p-0-0/survey", params={"party": "player"})
    assert rs.status_code == 200
    assert rs.json().get("terrain") == "plains"
    import realm.api as api

    grant_turnkey_self_materials(api._world, PartyId("player"), "wood_shop")
    rb = c.post(
        "/plots/p-0-0/build",
        params={"building_id": "wood_shop", "party": "player", "build_mode": "turnkey"},
    )
    assert rb.status_code == 200
    for _ in range(400):
        c.post("/tick")
    wj = c.get("/world").json()
    plot = next(p for p in wj["plots"] if p["id"] == "p-0-0")
    rids = plot.get("recipe_ids") or []
    assert isinstance(rids, list)
    assert "sawmill" in rids
    assert len(rids) >= 3


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
    row.pop("completes_at_tick", None)
    row["condition_bps"] = 500
    total_before = api._world.ledger.total_cents()
    r = c.post(
        "/plots/p-0-0/maintain",
        params={"party": "player", "instance_id": str(row["instance_id"])},
    )
    assert r.status_code == 200
    assert api._world.ledger.total_cents() == total_before
    assert row["condition_bps"] == BUILDING_CONDITION_FULL_BPS


def test_llm_status_lists_margaux() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 77})
    r = c.get("/llm/status")
    assert r.status_code == 200
    body = r.json()
    parties = {a["party"] for a in body["agents"]}
    assert "llm_margaux" in parties
    assert "client_ready" in body
    assert "model" in body
    assert "session_cap_micro_usd" in body
    assert "session_spend_micro_usd" in body


def test_code_status_stub() -> None:
    c = TestClient(app)
    r = c.get("/code/status")
    assert r.status_code == 200
    j = r.json()
    assert j.get("phase") == "stub"
    assert isinstance(j.get("lua_runtime"), bool)
    assert "lua" in j


def test_code_validate_http() -> None:
    c = TestClient(app)
    r = c.post("/code/validate", json={"source": "print('x')\n"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("lines") == 2
    r2 = c.post("/code/validate", json={})
    assert r2.status_code == 400


def test_code_deploy_and_world_summary() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 201})
    r = c.post("/code/deploy", json={"party": "player", "source": "-- x\nreturn tick\n"})
    assert r.status_code == 200
    assert r.json().get("ok") is True
    w = c.get("/world").json()
    assert "deployed_lua" in w
    assert "player" in w["deployed_lua"]
    assert w["deployed_lua"]["player"]["chars"] > 0


def test_code_eval_without_env_returns_reason() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 202})
    r = c.post("/code/eval", json={"source": "return 1"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is False


def test_pre_ui_api_alias_routes_smoke() -> None:
    """Thin parity routes for the Phase 11 UI (no duplicate game logic)."""
    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 203})
    r1 = c.get("/businesses/templates")
    assert r1.status_code == 200
    assert r1.json().get("ok") is True
    assert isinstance(r1.json().get("templates"), list)
    r2 = c.get("/businesses/mine", params={"party": "player"})
    assert r2.status_code == 200
    assert r2.json().get("ok") is True
    r3 = c.get("/construction/orders")
    assert r3.status_code == 200
    assert r3.json().get("ok") is True
    r4 = c.get("/science/elements")
    assert r4.status_code == 200
    assert r4.json().get("ok") is True
    r5 = c.get("/science/reactions/discovered", params={"party": "player"})
    assert r5.status_code == 200
    assert r5.json().get("ok") is True

"""Labs API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realm.api import app

client = TestClient(app)


def test_labs_presets_list() -> None:
    r = client.get("/labs/presets?limit=10&featured_only=true")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["total"] >= 35
    assert len(j["presets"]) <= 10
    assert "Markets" in j["categories"]


def test_labs_preset_detail() -> None:
    r = client.get("/labs/presets/feat_tutorial_first_claim")
    assert r.status_code == 200
    j = r.json()
    assert j["preset"]["id"] == "feat_tutorial_first_claim"
    assert "override_schema" in j["preset"]


def test_labs_start_and_world_dto() -> None:
    r = client.post(
        "/labs/start",
        json={
            "preset_id": "feat_p2p_micro",
            "seed": 123,
            "overrides": {"sim_speed": 2},
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["lab_mode"] is True
    assert j["lab_preset_id"] == "feat_p2p_micro"
    assert "labs/" in j["default_save_slot"]

    w = client.get("/world")
    assert w.status_code == 200
    wd = w.json()
    assert wd.get("lab_mode") is True
    assert wd.get("lab_preset_id") == "feat_p2p_micro"


def test_labs_exit() -> None:
    client.post("/labs/start", json={"preset_id": "gen_quick_frontier_8x6"})
    r = client.post("/labs/exit?scenario=frontier&seed=1")
    assert r.status_code == 200
    assert r.json()["lab_mode"] is False
    w = client.get("/world")
    assert w.json().get("lab_mode") is False

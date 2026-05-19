"""POST /dev/reset wires `scenario` query into bootstrap_by_scenario."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realm.api import _state, app
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS
from realm.world.plot_parcels import world_map_tile_count


@pytest.mark.parametrize(
    "scenario,expected_map_tiles,expected_player_cents,expect_cartel_cell",
    [
        ("frontier", 48 * 36, PLAYER_STARTING_CASH_CENTS, False),
        ("bootstrapper", 32 * 24, 485_000, False),
        ("speculator", 40 * 30, 2_050_000, False),
        ("cartel", 48 * 36, PLAYER_STARTING_CASH_CENTS, True),
        ("millrace", 42 * 28, 975_000, False),
        ("archive", 48 * 36, 1_080_000, False),
        ("genesis", 320 * 240, PLAYER_STARTING_CASH_CENTS, False),
    ],
)
def test_dev_reset_applies_scenario_params(
    scenario: str,
    expected_map_tiles: int,
    expected_player_cents: int,
    expect_cartel_cell: bool,
) -> None:
    c = TestClient(app)
    r = c.post("/dev/reset", params={"seed": 123, "scenario": scenario})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j["scenario_id"] == scenario
    assert j["seed"] == 123
    assert j["player_cash_cents"] == expected_player_cents
    if scenario in ("frontier", "cartel", "genesis"):
        assert j["player_starting_cash_cents"] == PLAYER_STARTING_CASH_CENTS

    world = _state.WORLD
    assert world_map_tile_count(world) == expected_map_tiles
    player_cash = world.ledger.balance(party_cash_account(PartyId("player")))
    assert player_cash == expected_player_cents
    grain_orders = world.market_asks_by_material.get(MaterialId("grain"), [])
    grain_parties = {str(o.party) for o in grain_orders}
    assert ("cartel_grain_cell" in grain_parties) == expect_cartel_cell
    if scenario == "genesis":
        assert "genesis_exchange" in grain_parties


def test_dev_reset_unknown_scenario_returns_400() -> None:
    c = TestClient(app)
    r = c.post("/dev/reset", params={"seed": 1, "scenario": "not_a_named_scenario"})
    assert r.status_code == 400


def test_dev_reset_scenario_query_is_case_insensitive() -> None:
    c = TestClient(app)
    r = c.post("/dev/reset", params={"seed": 7, "scenario": "Frontier"})
    assert r.status_code == 200
    assert r.json()["scenario_id"] == "frontier"


def test_dev_reset_defaults_to_genesis() -> None:
    c = TestClient(app)
    r = c.post("/dev/reset", params={"seed": 42})
    assert r.status_code == 200
    assert r.json()["scenario_id"] == "genesis"
    assert _state.WORLD.scenario_id == "genesis"
    assert world_map_tile_count(_state.WORLD) == 320 * 240


def test_persistence_list_returns_ok_and_slots() -> None:
    c = TestClient(app)
    r = c.get("/persistence/list")
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert isinstance(j.get("slots"), list)


def test_persistence_save_load_roundtrip_with_meta(tmp_path, monkeypatch) -> None:
    """Save → list → load preserves tick and exposes meta (scenario/seed/saved_at)."""
    monkeypatch.setattr(_state, "_SAVES_DIR", tmp_path)
    monkeypatch.setattr(_state, "_DEFAULT_SAVE_PATH", tmp_path / "realm_dev.sqlite")
    monkeypatch.setattr(_state, "_AUTOSAVE_PATH", tmp_path / "autosave.sqlite")
    monkeypatch.setattr(_state, "_REPO_ROOT", tmp_path.parent)

    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 9, "scenario": "frontier"})
    saved_tick = _state.WORLD.tick

    rs = c.post("/persistence/save", params={"slot": "unit_test_slot"})
    assert rs.status_code == 200
    assert rs.json()["ok"] is True

    rl = c.get("/persistence/list")
    slots = rl.json()["slots"]
    match = [s for s in slots if s["name"] == "unit_test_slot"]
    assert match, f"slot not in list: {slots}"
    meta = match[0]
    assert meta["scenario_id"] == "frontier"
    assert meta["seed"] == 9
    assert meta["tick"] == saved_tick
    assert meta["saved_at"] > 0

    rld = c.post("/persistence/load", params={"slot": "unit_test_slot"})
    assert rld.status_code == 200
    assert rld.json()["ok"] is True
    assert _state.WORLD.tick == saved_tick


def test_persistence_save_rejects_path_outside_saves(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_state, "_SAVES_DIR", tmp_path)
    monkeypatch.setattr(_state, "_REPO_ROOT", tmp_path.parent)

    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 1, "scenario": "frontier"})
    r = c.post("/persistence/save", params={"path": "../escape.sqlite"})
    assert r.status_code == 400


def test_persistence_status_reports_last_save(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_state, "_SAVES_DIR", tmp_path)
    monkeypatch.setattr(_state, "_DEFAULT_SAVE_PATH", tmp_path / "realm_dev.sqlite")
    monkeypatch.setattr(_state, "_AUTOSAVE_PATH", tmp_path / "autosave.sqlite")
    monkeypatch.setattr(_state, "_REPO_ROOT", tmp_path.parent)

    c = TestClient(app)
    c.post("/dev/reset", params={"seed": 1, "scenario": "frontier"})
    c.post("/persistence/save", params={"slot": "status_probe"})
    s = c.get("/persistence/status").json()
    assert s["ok"] is True
    assert s["last_save_at"] > 0
    assert s["last_save_kind"] == "manual"
    assert s["world_initialized"] is True

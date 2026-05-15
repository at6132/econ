"""POST /dev/reset wires `scenario` query into bootstrap_by_scenario."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realm.api import app


@pytest.mark.parametrize(
    "scenario,expected_plots,expected_player_cents,expect_cartel_cell",
    [
        ("frontier", 48 * 36, 1_000_000, False),
        ("bootstrapper", 32 * 24, 485_000, False),
        ("speculator", 40 * 30, 2_050_000, False),
        ("cartel", 48 * 36, 1_000_000, True),
        ("millrace", 42 * 28, 975_000, False),
        ("archive", 48 * 36, 1_080_000, False),
        ("genesis", 96 * 72, 1_000_000, False),
    ],
)
def test_dev_reset_applies_scenario_params(
    scenario: str,
    expected_plots: int,
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

    w = c.get("/world")
    assert w.status_code == 200
    body = w.json()
    assert body["scenario_id"] == scenario
    assert len(body["plots"]) == expected_plots
    assert body["balances_cents"]["cash:player"] == expected_player_cents
    grain_parties = {row["party"] for row in body["market_asks"] if row["material"] == "grain"}
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
    w = c.get("/world").json()
    assert w["scenario_id"] == "genesis"
    assert len(w["plots"]) == 96 * 72

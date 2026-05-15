"""POST /dev/reset wires `scenario` query into bootstrap_by_scenario."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realm.api import _state, app
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account


@pytest.mark.parametrize(
    "scenario,expected_plots,expected_player_cents,expect_cartel_cell",
    [
        ("frontier", 48 * 36, 1_000_000, False),
        ("bootstrapper", 32 * 24, 485_000, False),
        ("speculator", 40 * 30, 2_050_000, False),
        ("cartel", 48 * 36, 1_000_000, True),
        ("millrace", 42 * 28, 975_000, False),
        ("archive", 48 * 36, 1_080_000, False),
        ("genesis", 192 * 144, 1_000_000, False),
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

    world = _state.WORLD
    assert len(world.plots) == expected_plots
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
    assert len(_state.WORLD.plots) == 192 * 144

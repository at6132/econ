"""Cartel scenario bootstrap."""

from __future__ import annotations

from realm.world import bootstrap_by_scenario


def test_cartel_scenario_splits_grain_book() -> None:
    w = bootstrap_by_scenario(seed=44, scenario="cartel")
    assert w.scenario_id == "cartel"
    grain_asks = w.market_asks_by_material.get("grain", [])
    parties = {str(o.party) for o in grain_asks}
    assert "cartel_grain_cell" in parties
    assert "npc_grain_vendor" in parties
    prices = sorted(o.price_per_unit_cents for o in grain_asks)
    assert prices[0] < prices[-1]

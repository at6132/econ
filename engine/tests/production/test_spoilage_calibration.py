"""Realism pass 7B — spoilage intervals, store restock, perishable NPC sales, oracle."""

from __future__ import annotations

import pytest

from realm.agents.market_oracle import (
    _build_oracle,
    _input_cost_cents,
    _output_value_cents,
)
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.genesis.settler_upgrades import _maybe_sell_perishables
from realm.materials import MATERIALS
from realm.population.laborers import TICKS_PER_GAME_DAY
from realm.population.stores import (
    NPC_STORE_GRAIN_QTY,
    restock_target_qty,
)
from realm.production.recipes import RECIPES
from realm.world import bootstrap_genesis


def test_grain_does_not_spoil_within_3_days() -> None:
    """Recalibrated grain interval is well beyond a 3-day stockpile window."""
    grain = MATERIALS.get(MaterialId("grain"))
    assert grain is not None
    interval = int(grain.spoilage_interval_ticks)
    new_days = interval / TICKS_PER_GAME_DAY
    assert new_days >= 5.0, f"Grain should spoil in ≥5 days, got {new_days:.1f}"
    assert 3 * TICKS_PER_GAME_DAY < interval


def test_store_restock_respects_spoilage_window() -> None:
    """Restock target scales with sales × spoilage window, not a flat 250."""
    w = bootstrap_genesis(seed=4, settler_count=8)
    store_pid = next(iter(w.store_inventories.keys()))
    daily_rate = 12.0
    history = w.scenario_state.setdefault("store_sales_history", {})
    plot_history: list[dict] = []
    for day in range(7):
        plot_history.append({"day": day, "sales": {"grain": int(daily_rate)}})
    history[store_pid] = plot_history

    target = restock_target_qty(w, store_pid, "grain", default_restock=250)
    spoil_days = MATERIALS[MaterialId("grain")].spoilage_interval_ticks / TICKS_PER_GAME_DAY
    assert target <= daily_rate * spoil_days * 1.1
    assert target < NPC_STORE_GRAIN_QTY


def test_settler_lists_perishable_before_spoilage() -> None:
    """Plot-staged grain is listed for sale the same day."""
    w = bootstrap_genesis(seed=2, settler_count=3)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    settler = next(p for p in w.parties if str(p).startswith("settler_"))
    pid_s: str | None = None
    for row in w.plot_buildings:
        if str(row.get("party")) == str(settler):
            pid_s = str(row.get("plot_id", ""))
            break
    if not pid_s:
        pid_s = str(next(iter(w.plots)))
    plot = w.plots[PlotId(pid_s)]
    plot.owner = settler
    w.plot_output_stock.setdefault(pid_s, {})["grain"] = 20
    n = _maybe_sell_perishables(w, settler)
    assert n >= 1, "Settler should immediately list perishable grain"
    listed = sum(
        int(a.qty)
        for asks in w.market_asks_by_material.values()
        for a in asks
        if a.party == settler and str(a.material) == "grain"
    )
    assert listed >= 1
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_oracle_discounts_perishable_recipes() -> None:
    """grow_grain margin is reduced vs undiscounted spot-margin math."""
    w = bootstrap_genesis(seed=3, settler_count=3)
    oracle = _build_oracle(w, 0)
    rid = "grow_grain"
    assert rid in RECIPES
    recipe = RECIPES[rid]
    input_cost = _input_cost_cents(oracle, recipe)
    output_value = _output_value_cents(oracle, recipe)
    assert input_cost > 0
    raw_margin = (output_value - input_cost) / input_cost
    discounted = oracle.recipe_margins.get(rid, 0.0)
    assert discounted < raw_margin
    assert discounted == pytest.approx(raw_margin * 0.75, rel=0.02)

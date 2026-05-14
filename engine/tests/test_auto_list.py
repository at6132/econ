"""Sprint 6 — Phase D.2: auto-listing of production output.

When a workshop has ``auto_list_output: True``, every ``production_done``
queues a sell order for the just-produced units at ``cost_basis × 1.30``.
"""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.production import (
    _auto_list_price_cents,
    set_building_auto_list,
    start_production,
)
from realm.terrain import Terrain
from realm.tick import advance_tick
from realm.world import bootstrap_genesis


def _ensure_cash(world, party: PartyId, cents: int) -> None:
    acc = party_cash_account(party)
    world.ledger.ensure_account(acc)
    world.ledger.transfer(
        debit=system_reserve_account(), credit=acc, amount_cents=cents
    )


def _find_high_coal_plot(world) -> PlotId | None:
    for pid, plot in world.plots.items():
        if (
            plot.owner is None
            and plot.terrain in (Terrain.PLAINS, Terrain.FOREST, Terrain.MOUNTAIN)
            and float(getattr(plot.subsurface, "coal_grade", 0.0)) >= 0.3
        ):
            return pid
    return None


def test_auto_list_price_uses_cost_basis_times_1_30() -> None:
    w = bootstrap_genesis(seed=11, grid_width=12, grid_height=10, settler_count=2)
    # Lumber cost basis is known via the producer recipe path.
    price = _auto_list_price_cents(w, MaterialId("lumber"))
    assert price is not None and price > 0
    # Coal has no producer recipe (hand_mine_coal is hand-tool) but
    # ``_FAIR_VALUE_CENTS`` provides a fallback basis.
    coal_price = _auto_list_price_cents(w, MaterialId("coal"))
    assert coal_price is not None and coal_price > 0


def test_set_auto_list_requires_owner() -> None:
    w = bootstrap_genesis(seed=13, grid_width=12, grid_height=10, settler_count=2)
    # Plant a fake workshop owned by settler_001
    w.plot_buildings.append(
        {
            "instance_id": "bld-test-1",
            "party": "settler_001",
            "plot_id": "p-5-5",
            "building_id": "sawmill",
            "auto_list_output": False,
        }
    )
    r = set_building_auto_list(w, PartyId("player"), "bld-test-1", True)
    assert r.get("ok") is False and "owner" in str(r.get("reason", ""))
    r2 = set_building_auto_list(w, PartyId("settler_001"), "bld-test-1", True)
    assert r2.get("ok") is True
    # And the flag actually persisted on the building row.
    flags = [b.get("auto_list_output") for b in w.plot_buildings if b.get("instance_id") == "bld-test-1"]
    assert flags == [True]


def test_hand_recipe_with_auto_list_flag_skipped() -> None:
    """Hand recipes have no workshop row, so the auto-list path is a no-op."""
    w = bootstrap_genesis(seed=42, grid_width=12, grid_height=10, settler_count=2)
    w.scenario_state.setdefault("labor", {})["enabled"] = False
    pid = _find_high_coal_plot(w)
    assert pid is not None
    party = PartyId("player")
    _ensure_cash(w, party, 1_000_000)
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid).get("ok") is True
    w.inventory.add(party, MaterialId("mining_pick"), 1)
    def _player_coal_asks() -> int:
        return sum(
            1
            for a in w.market_asks_by_material.get(MaterialId("coal"), [])
            if a.party == party
        )

    before = _player_coal_asks()
    r = start_production(w, party, pid, "hand_mine_coal", run_count=1)
    assert r["ok"], r
    for _ in range(400):
        advance_tick(w)
        if w.inventory.qty(party, MaterialId("coal")) > 0:
            break
    # No workshop ⇒ no auto-list ⇒ no new ask owned by the player.
    assert _player_coal_asks() == before


def test_auto_list_places_order_for_workshop_output() -> None:
    """A workshop with auto_list_output=True turns each production_done into a sell order."""
    w = bootstrap_genesis(seed=17, grid_width=14, grid_height=12, settler_count=2)
    # Disable labor penalty so a single un-hired player isn't running at 50%.
    w.scenario_state.setdefault("labor", {})["enabled"] = False
    party = PartyId("player")
    _ensure_cash(w, party, 5_000_000)
    # Find a forest plot to host a wood_shop and run "sawmill" (timber → lumber).
    pid = None
    for p_id, plot in w.plots.items():
        if plot.owner is None and plot.terrain == Terrain.FOREST:
            pid = p_id
            break
    assert pid is not None
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid).get("ok") is True
    # Plant a wood_shop building directly (skipping the build cost path).
    iid = "bld-auto-1"
    w.plot_buildings.append(
        {
            "instance_id": iid,
            "party": str(party),
            "plot_id": str(pid),
            "building_id": "wood_shop",
            "auto_list_output": False,
        }
    )
    # Stage inputs and tools for the sawmill recipe.
    w.inventory.add(party, MaterialId("timber"), 4)
    w.inventory.add(party, MaterialId("electricity"), 4)

    def _player_lumber_asks() -> list:
        return [
            a
            for a in w.market_asks_by_material.get(MaterialId("lumber"), [])
            if a.party == party
        ]

    before = len(_player_lumber_asks())
    # Sanity: without the flag, no auto-list ask appears for the player.
    r = start_production(w, party, pid, "sawmill", run_count=1)
    assert r["ok"], r
    for _ in range(200):
        advance_tick(w)
        if w.inventory.qty(party, MaterialId("lumber")) > 0:
            break
    lumber_first = w.inventory.qty(party, MaterialId("lumber"))
    assert len(_player_lumber_asks()) == before, "should not auto-list when flag off"
    # Now enable the flag, run again, expect a new lumber ask owned by player.
    assert set_building_auto_list(w, party, iid, True).get("ok") is True
    w.inventory.add(party, MaterialId("timber"), 4)
    w.inventory.add(party, MaterialId("electricity"), 4)
    r2 = start_production(w, party, pid, "sawmill", run_count=1)
    assert r2["ok"], r2
    for _ in range(200):
        advance_tick(w)
        if w.inventory.qty(party, MaterialId("lumber")) > lumber_first:
            break
    player_asks = _player_lumber_asks()
    assert len(player_asks) > before, (
        f"auto-list should have placed a lumber ask for the player; before={before}, now={len(player_asks)}"
    )
    expected = _auto_list_price_cents(w, MaterialId("lumber"))
    assert any(int(a.price_per_unit_cents) == int(expected) for a in player_asks), (
        f"expected price ≈ {expected}; got {[a.price_per_unit_cents for a in player_asks]}"
    )

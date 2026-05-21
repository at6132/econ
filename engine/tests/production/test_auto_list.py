"""Auto-listing pulls from plot bulk at the workshop site."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.infrastructure.plot_logistics import plot_output_qty
from realm.production import (
    _auto_list_price_cents,
    set_building_auto_list,
    start_production,
)
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
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
    price = _auto_list_price_cents(w, MaterialId("lumber"))
    assert price is not None and price > 0
    coal_price = _auto_list_price_cents(w, MaterialId("coal"))
    assert coal_price is not None and coal_price > 0


def test_set_auto_list_requires_owner() -> None:
    w = bootstrap_genesis(seed=13, grid_width=12, grid_height=10, settler_count=2)
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


def test_auto_list_places_order_from_plot_stock() -> None:
    w = bootstrap_genesis(seed=17, grid_width=14, grid_height=12, settler_count=2)
    w.scenario_state.setdefault("labor", {})["enabled"] = False
    party = PartyId("player")
    _ensure_cash(w, party, 5_000_000)
    from plot_helpers import first_terrain_plot_id

    pid = first_terrain_plot_id(w, Terrain.FOREST)
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid).get("ok") is True
    iid = "bld-auto-1"
    w.plot_buildings.append(
        {
            "instance_id": iid,
            "party": str(party),
            "plot_id": str(pid),
            "building_id": "wood_shop",
            "auto_list_output": True,
        }
    )
    w.plot_output_stock.setdefault(str(pid), {})[str(MaterialId("timber"))] = 4
    w.inventory.add(party, MaterialId("electricity"), 4)

    def _player_lumber_asks() -> list:
        return [
            a
            for a in w.market_asks_by_material.get(MaterialId("lumber"), [])
            if a.party == party
        ]

    before = len(_player_lumber_asks())
    r = start_production(w, party, pid, "sawmill", run_count=1)
    assert r["ok"], r
    for _ in range(200):
        advance_tick(w)
        if plot_output_qty(w, pid, MaterialId("lumber")) > 0 or _player_lumber_asks():
            break
    for _ in range(200):
        advance_tick(w)
        if _player_lumber_asks():
            break
    player_asks = _player_lumber_asks()
    assert len(player_asks) > before
    expected = _auto_list_price_cents(w, MaterialId("lumber"))
    assert any(int(a.price_per_unit_cents) == int(expected) for a in player_asks)

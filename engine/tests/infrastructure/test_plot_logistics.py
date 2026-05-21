"""Plot-local bulk storage (Option B) — matter lives on plots, not in global carry."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.infrastructure.movement import dispatch_shipment
from realm.infrastructure.plot_logistics import plot_output_qty
from realm.production.storage_caps import is_carried_material
from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis, bootstrap_frontier


def test_genesis_enables_plot_logistics() -> None:
    w = bootstrap_genesis(seed=7, grid_width=10, grid_height=8, settler_count=2)
    assert w.use_plot_output_logistics is True


def test_dispatch_pulls_from_plot_stock_and_delivers_to_dest_plot() -> None:
    w = bootstrap_genesis(seed=13, grid_width=12, grid_height=10, settler_count=2)
    party = PartyId("player")
    claimed: list[PlotId] = []
    for pid, plot in w.plots.items():
        if plot.owner is not None:
            continue
        if str(plot.terrain) == "ocean":
            continue
        r = claim_plot(w, party, pid)
        if r.get("ok"):
            claimed.append(pid)
        if len(claimed) >= 2:
            break
    assert len(claimed) >= 2
    a, b = claimed[0], claimed[1]
    w.plot_output_stock[str(a)] = {str(MaterialId("coal")): 20}
    r = dispatch_shipment(w, party, MaterialId("coal"), 12, a, b)
    assert r["ok"] is True, r
    assert plot_output_qty(w, a, MaterialId("coal")) == 8
    assert w.inventory.qty(party, MaterialId("coal")) == 0
    for _ in range(200):
        advance_tick(w)
        if plot_output_qty(w, b, MaterialId("coal")) >= 12:
            break
    assert plot_output_qty(w, b, MaterialId("coal")) >= 12, (
        f"coal at dest={plot_output_qty(w, b, MaterialId('coal'))}, "
        f"in_transit={len(w.in_transit)}"
    )


def test_production_output_lands_on_plot_not_carry() -> None:
    from realm.actions import survey_plot
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.production import start_production
    from realm.world.terrain import Terrain

    w = bootstrap_genesis(seed=42, grid_width=12, grid_height=10, settler_count=2)
    party = PartyId("player")
    w.scenario_state.setdefault("labor", {})["enabled"] = False
    pid = None
    for p_id, plot in w.plots.items():
        if (
            plot.owner is None
            and plot.terrain in (Terrain.PLAINS, Terrain.FOREST, Terrain.MOUNTAIN)
            and float(getattr(plot.subsurface, "coal_grade", 0.0)) >= 0.3
        ):
            pid = p_id
            break
    assert pid is not None
    cash = party_cash_account(party)
    w.ledger.ensure_account(cash)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=cash, amount_cents=1_000_000
    )
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid).get("ok") is True
    w.inventory.add(party, MaterialId("mining_pick"), 1)
    w.plot_output_stock.setdefault(str(pid), {})[str(MaterialId("coal"))] = 0
    r = start_production(w, party, pid, "hand_mine_coal", run_count=1)
    assert r["ok"], r
    for _ in range(400):
        advance_tick(w)
        if plot_output_qty(w, pid, MaterialId("coal")) > 0:
            break
    assert plot_output_qty(w, pid, MaterialId("coal")) > 0
    assert w.inventory.qty(party, MaterialId("coal")) == 0


def test_frontier_starter_bulk_on_spawn_plot() -> None:
    w = bootstrap_frontier(seed=99, grid_width=20, grid_height=16)
    party = PartyId("player")
    spawn = PlotId("p-10-8")
    assert w.plots[spawn].owner == party
    assert plot_output_qty(w, spawn, MaterialId("timber")) >= 12
    assert w.inventory.qty(party, MaterialId("electricity")) >= 8
    assert not is_carried_material(MaterialId("timber"))

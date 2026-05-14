"""Sprint 6 — Phase D.1: ``plot_output_stock`` is now a cumulative *display log*.

Matter always lives in ``world.inventory.stock[party][material]``. The
``plot_output_stock`` dict records per-plot production + delivery counters so
the UI can show "what was produced here" — but it is never the source of
truth for matter.
"""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.infrastructure.movement import dispatch_shipment
from realm.infrastructure.plot_logistics import plot_output_qty
from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis


def test_genesis_enables_plot_logistics_display_log() -> None:
    w = bootstrap_genesis(seed=7, grid_width=10, grid_height=8, settler_count=2)
    # The flag is still on — it gates the cumulative display log writes.
    assert w.use_plot_output_logistics is True


def test_dispatch_pulls_from_party_inventory_and_logs_destination_stock() -> None:
    w = bootstrap_genesis(seed=13, grid_width=12, grid_height=10, settler_count=2)
    a = PlotId("p-0-0")
    b = PlotId("p-1-0")
    party = PartyId("player")
    assert claim_plot(w, party, a)["ok"] is True
    assert claim_plot(w, party, b)["ok"] is True
    # Stage coal in party inventory directly.
    w.inventory.add(party, MaterialId("coal"), 20)
    r = dispatch_shipment(w, party, MaterialId("coal"), 12, a, b)
    assert r["ok"] is True, r
    # Inventory drained by qty shipped.
    assert w.inventory.qty(party, MaterialId("coal")) == 8
    for _ in range(60):
        if w.inventory.qty(party, MaterialId("coal")) >= 20:
            break
        advance_tick(w)
    # After arrival, the 12 units land back in inventory.
    assert w.inventory.qty(party, MaterialId("coal")) == 20
    # The destination plot's display log records the delivery.
    assert plot_output_qty(w, b, MaterialId("coal")) >= 12


def test_player_can_list_freshly_produced_goods_from_inventory() -> None:
    """Phase D.1 fix: production output appears in party inventory directly so
    the player can immediately list it on the market without harvesting."""
    from realm.actions import survey_plot
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.production import start_production
    from realm.world.terrain import Terrain

    w = bootstrap_genesis(seed=42, grid_width=12, grid_height=10, settler_count=2)
    party = PartyId("player")
    # Disable the labor staffing penalty so a single un-hired player still gets
    # full output. (Sprint 3 added a 50% understaffing modifier.)
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
    starting = w.inventory.qty(party, MaterialId("coal"))
    r = start_production(w, party, pid, "hand_mine_coal", run_count=1)
    assert r["ok"], r
    for _ in range(400):
        advance_tick(w)
        if w.inventory.qty(party, MaterialId("coal")) > starting:
            break
    # Coal appears in party inventory (not just in plot_output_stock).
    assert w.inventory.qty(party, MaterialId("coal")) > starting, (
        f"player inventory did not receive coal after production: "
        f"starting={starting}, now={w.inventory.qty(party, MaterialId('coal'))}"
    )

"""Extra commerce steps: delivery receiving fees (all parties); Genesis seller registration (all parties)."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.economy.markets import MARKET_SELLER_REGISTRATION_CENTS, place_sell_order
from realm.infrastructure.movement import dispatch_shipment, receiving_fee_cents
from realm.infrastructure.plot_logistics import try_add_plot_output
from realm.world.tick import advance_tick
from realm.world.terrain import Terrain
from realm.world import World, bootstrap_genesis


def _two_unowned_land_plots(w: World) -> tuple[PlotId, PlotId]:
    """Pick two distinct claimable plots (avoids NPC-seeded footprints like ``p-1-0``)."""
    ids = sorted(
        (
            p.plot_id
            for p in w.plots.values()
            if p.owner is None and p.terrain != Terrain.WATER_DEEP
        ),
        key=str,
    )
    if len(ids) < 2:
        raise AssertionError("bootstrap must yield at least two unowned land plots")
    return ids[0], ids[1]


def test_receiving_fee_scales_with_qty() -> None:
    assert receiving_fee_cents(1) == 25
    assert receiving_fee_cents(20) == 25
    assert receiving_fee_cents(21) == 26


def test_genesis_second_list_same_material_no_second_registration() -> None:
    w = bootstrap_genesis(seed=77, grid_width=8, grid_height=6, settler_count=0)
    p = PartyId("player")
    g = MaterialId("grain")
    from realm.actions import claim_plot
    from realm.infrastructure.plot_logistics import plot_output_qty

    pid = next(iter(w.plots.keys()))
    w.plots[pid].owner = p
    w.plot_output_stock[str(pid)] = {str(g): 20}
    assert plot_output_qty(w, pid, g) == 20
    pc = party_cash_account(p)
    b0 = w.ledger.balance(pc)
    assert place_sell_order(w, p, g, 4, 120)["ok"] is True
    b1 = w.ledger.balance(pc)
    assert b0 - b1 == MARKET_SELLER_REGISTRATION_CENTS
    assert place_sell_order(w, p, g, 3, 118)["ok"] is True
    b2 = w.ledger.balance(pc)
    assert b1 == b2


def test_delivery_deferred_when_insufficient_cash_for_receiving() -> None:
    w = bootstrap_genesis(seed=31, grid_width=10, grid_height=8, settler_count=0)
    a, b = _two_unowned_land_plots(w)
    p = PartyId("player")
    assert claim_plot(w, p, a)["ok"] is True
    assert claim_plot(w, p, b)["ok"] is True
    w.plot_output_stock[str(a)] = {str(MaterialId("coal")): 8}
    r = dispatch_shipment(w, p, MaterialId("coal"), 6, a, b)
    assert r["ok"] is True
    recv = receiving_fee_cents(6)
    pc = party_cash_account(p)
    bal = w.ledger.balance(pc)
    drain = max(0, bal - (recv - 5))
    if drain > 0:
        tr = w.ledger.transfer(debit=pc, credit=system_reserve_account(), amount_cents=drain)
        assert not isinstance(tr, MoneyErr)
    assert w.ledger.balance(pc) < recv
    for _ in range(55):
        advance_tick(w)
        if any(e.get("kind") == "ship_deliver_blocked" for e in w.event_log[-8:]):
            break
    assert len(w.in_transit) >= 1

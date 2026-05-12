"""Genesis plot-local staging: production/shipping deliver to plot stash; harvest → party inventory."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot, harvest_plot_output_stock
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.movement import dispatch_shipment
from realm.plot_logistics import plot_output_qty, try_add_plot_output
from realm.recipe_sites import terrain_allows_workshop
from realm.tick import advance_tick
from realm.world import bootstrap_genesis


def _player_matter_units(world) -> int:
    inv = sum(world.inventory.stock.get(PartyId("player"), {}).values())
    stash = 0
    for inner in world.plot_output_stock.values():
        stash += sum(int(v) for v in inner.values())
    return inv + stash


def test_genesis_enables_plot_logistics() -> None:
    w = bootstrap_genesis(seed=7, grid_width=10, grid_height=8, settler_count=2)
    assert w.use_plot_output_logistics is True


def test_harvest_moves_stash_to_inventory_conserves_matter() -> None:
    w = bootstrap_genesis(seed=11, grid_width=12, grid_height=10, settler_count=2)
    a = PlotId("p-0-0")
    b = PlotId("p-1-0")
    assert claim_plot(w, PartyId("player"), a)["ok"] is True
    assert claim_plot(w, PartyId("player"), b)["ok"] is True
    assert not isinstance(try_add_plot_output(w, a, PartyId("player"), MaterialId("iron_ore"), 40), MatterErr)
    t0 = _player_matter_units(w)
    assert harvest_plot_output_stock(w, PartyId("player"), a, "iron_ore", 15)["ok"] is True
    assert plot_output_qty(w, a, MaterialId("iron_ore")) == 25
    assert w.inventory.qty(PartyId("player"), MaterialId("iron_ore")) == 15
    assert _player_matter_units(w) == t0


def test_dispatch_draws_from_plot_stash_delivers_to_dest_stash() -> None:
    w = bootstrap_genesis(seed=13, grid_width=12, grid_height=10, settler_count=2)
    a = PlotId("p-0-0")
    b = PlotId("p-1-0")
    assert claim_plot(w, PartyId("player"), a)["ok"] is True
    assert claim_plot(w, PartyId("player"), b)["ok"] is True
    assert not isinstance(try_add_plot_output(w, a, PartyId("player"), MaterialId("coal"), 20), MatterErr)
    r = dispatch_shipment(w, PartyId("player"), MaterialId("coal"), 12, a, b)
    assert r["ok"] is True
    assert plot_output_qty(w, a, MaterialId("coal")) == 8
    assert w.inventory.qty(PartyId("player"), MaterialId("coal")) == 0
    for _ in range(40):
        if plot_output_qty(w, b, MaterialId("coal")) == 12:
            break
        advance_tick(w)
    else:
        pytest.fail("shipment did not arrive at destination plot stash")


def test_settler_can_harvest_staged_goods() -> None:
    w = bootstrap_genesis(seed=29, grid_width=16, grid_height=12, settler_count=2)
    sid = PartyId("settler_001")
    spid = next(
        (
            pl.plot_id
            for pl in w.plots.values()
            if pl.owner is None and terrain_allows_workshop(pl.terrain)
        ),
        None,
    )
    assert spid is not None
    assert claim_plot(w, sid, spid)["ok"] is True
    assert not isinstance(try_add_plot_output(w, spid, sid, MaterialId("grain"), 7), MatterErr)
    assert harvest_plot_output_stock(w, sid, spid, "grain", 4)["ok"] is True
    assert plot_output_qty(w, spid, MaterialId("grain")) == 3
    assert w.inventory.qty(sid, MaterialId("grain")) == 4

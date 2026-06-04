"""Grid utility contracts — NPC grid requires subscription; own gen is free."""

from __future__ import annotations

from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.infrastructure.grid_operators import seed_grid_operator
from realm.infrastructure.grid_utility import (
    connect_grid_utility,
    disconnect_grid_utility,
    party_may_draw_grid_energy,
)
from realm.infrastructure.power_grid import plot_has_grid_capacity
from realm.infrastructure.roads import build_road
from tests.infrastructure.test_power_grid import _build_world, _claim, _install_building


def _link_gen_to_consumer(world, gen_plot: PlotId, use_plot: PlotId, gen: PartyId) -> None:
    world.inventory.add(gen, MaterialId("lumber"), 4)
    world.inventory.add(gen, MaterialId("stone"), 4)
    assert build_road(world, gen, gen_plot, use_plot)["ok"]


def _register_provider(world, gen: PartyId, gen_plot: PlotId) -> None:
    assert seed_grid_operator(world, gen, gen_plot)["ok"]


def test_npc_grid_requires_contract_for_consumer() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_gen_to_consumer(world, gen_plot, use_plot, gen)
    _register_provider(world, gen, gen_plot)
    assert plot_has_grid_capacity(world, use_plot)
    assert not party_may_draw_grid_energy(world, consumer, use_plot)[0]
    _install_building(world, consumer, use_plot, "power_shed")
    assert party_may_draw_grid_energy(world, consumer, use_plot)[0]


def test_connect_then_draw_npc_grid() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _install_building(world, consumer, use_plot, "strip_mine")
    _link_gen_to_consumer(world, gen_plot, use_plot, gen)
    _register_provider(world, gen, gen_plot)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    conn = connect_grid_utility(
        world, consumer, use_plot, gen, rate_cents_per_kwh=42, agreed_to_terms=True
    )
    assert conn["ok"] is True
    assert_money_conserved(world.ledger, snap.ledger_total_cents)
    assert party_may_draw_grid_energy(world, consumer, use_plot)[0]


def test_disconnect_blocks_grid_draw() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_gen_to_consumer(world, gen_plot, use_plot, gen)
    _register_provider(world, gen, gen_plot)
    conn = connect_grid_utility(world, consumer, use_plot, gen, agreed_to_terms=True)
    assert conn["ok"]
    cid = str(conn["connection_id"])
    assert disconnect_grid_utility(world, consumer, cid)["ok"]
    assert not party_may_draw_grid_energy(world, consumer, use_plot)[0]

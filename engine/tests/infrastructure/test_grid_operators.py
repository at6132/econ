"""Grid utility operator franchise registration."""

from __future__ import annotations

from realm.actions import register_business
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.infrastructure.grid_operators import (
    GRID_UTILITY_FRANCHISE_FEE_CENTS,
    list_grid_operators,
    register_grid_operator,
    seed_grid_operator,
)
from realm.infrastructure.grid_utility import (
    connect_grid_utility,
    preview_utility_contract,
    utility_provider_offers_for_plot,
)
from realm.infrastructure.roads import build_road
from tests.infrastructure.test_power_grid import _build_world, _claim, _install_building


def _link_plots(world, a: PlotId, b: PlotId, party: PartyId) -> None:
    world.inventory.add(party, MaterialId("lumber"), 4)
    world.inventory.add(party, MaterialId("stone"), 4)
    assert build_road(world, party, a, b)["ok"]


def test_unregistered_generator_not_in_provider_offers() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_plots(world, gen_plot, use_plot, gen)
    assert utility_provider_offers_for_plot(world, consumer, use_plot) == []
    assert seed_grid_operator(world, gen, gen_plot)["ok"]
    offers = utility_provider_offers_for_plot(world, consumer, use_plot)
    assert len(offers) == 1
    assert offers[0]["provider_party"] == str(gen)


def test_human_register_requires_business() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_plots(world, gen_plot, use_plot, gen)
    r = register_grid_operator(world, gen, gen_plot, rate_cents_per_kwh=15)
    assert not r["ok"]
    assert "business" in r["reason"].lower()
    register_business(world, gen, "Spark Grid LLC", "")
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    r2 = register_grid_operator(world, gen, gen_plot, rate_cents_per_kwh=15)
    assert r2["ok"]
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_connect_rejects_unregistered_provider() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_plots(world, gen_plot, use_plot, gen)
    assert not connect_grid_utility(
        world, consumer, use_plot, gen, agreed_to_terms=True
    )["ok"]
    assert seed_grid_operator(world, gen, gen_plot)["ok"]
    assert connect_grid_utility(
        world, consumer, use_plot, gen, agreed_to_terms=True
    )["ok"]


def test_preview_uses_operator_tariff() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_plots(world, gen_plot, use_plot, gen)
    assert seed_grid_operator(world, gen, gen_plot, rate_cents_per_kwh=33)["ok"]
    prev = preview_utility_contract(world, consumer, use_plot, gen)
    assert prev["ok"]
    assert prev["rate_cents_per_kwh"] == 33


def test_franchise_fee_charged_on_register() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_plots(world, gen_plot, use_plot, gen)
    register_business(world, gen, "Fee Test Power", "")
    from realm.core.ledger import party_cash_account

    before = world.ledger.balance(party_cash_account(gen))
    assert register_grid_operator(world, gen, gen_plot, rate_cents_per_kwh=12)["ok"]
    after = world.ledger.balance(party_cash_account(gen))
    assert before - after == GRID_UTILITY_FRANCHISE_FEE_CENTS


def test_list_operators_by_region() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _link_plots(world, gen_plot, use_plot, gen)
    assert seed_grid_operator(world, gen, gen_plot)["ok"]
    ops = list_grid_operators(world)
    assert len(ops) >= 1
    assert any(str(o["operator_party"]) == str(gen) for o in ops)

"""Corporations — partnership formation and acquisition buyouts conserve money."""

from __future__ import annotations

from realm.agents.settler_identity import assign_settler_personality, get_settler_world_model
from realm.core.conservation import (
    ConservationSnapshot,
    assert_money_conserved,
    assert_matter_conserved,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.corporations.acquisitions import execute_buyout, liquidation_value_cents
from realm.corporations.formation import propose_partnership
from realm.corporations.company import get_company
from realm.world import World, bootstrap_genesis, claim_cost_cents_for_plot
from realm.world.placed_buildings import PlacedBuilding, register_placed_building


def _seed_settler_cash(world: World, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    world.ledger.ensure_account(acct)
    reserve = system_reserve_account()
    world.ledger.transfer(debit=reserve, credit=acct, amount_cents=cents)


def _pick_two_settlers(world: World) -> tuple[PartyId, PartyId]:
    settlers = sorted(p for p in world.parties if str(p).startswith("settler_"))
    assert len(settlers) >= 2
    return settlers[0], settlers[1]


def _mutual_reputation(world: World, a: PartyId, b: PartyId) -> None:
    world.reputation[str(a)] = {"honored": 8, "breached": 0}
    world.reputation[str(b)] = {"honored": 7, "breached": 0}


def _inject_known_settlers(world: World, observer: PartyId, other: PartyId, *, material: str) -> None:
    from realm.agents.settler_identity import _store_world_model

    model = get_settler_world_model(world, observer)
    model.known_settlers[str(other)] = {
        "estimated_cash_tier": "high",
        "primary_material": material,
        "plot_ids": [],
        "reputation_score": 8,
    }
    _store_world_model(world, observer, model)


def test_partnership_formation_conserves_money() -> None:
    world = bootstrap_genesis(seed=42, grid_width=32, grid_height=24, settler_count=4)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    a, b = _pick_two_settlers(world)
    assign_settler_personality(world, a)
    assign_settler_personality(world, b)
    _mutual_reputation(world, a, b)
    _seed_settler_cash(world, a, 350_000)
    _seed_settler_cash(world, b, 350_000)
    _inject_known_settlers(world, a, b, material="coal")
    _inject_known_settlers(world, b, a, material="iron_ingot")

    result = propose_partnership(world, a, b)
    assert result["ok"], result
    company = get_company(world, result["company_id"])
    assert company is not None
    assert company.total_shares == 1000
    assert company.share_registry[str(a)] == 500
    assert company.share_registry[str(b)] == 500

    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_buyout_conserves_money_and_transfers_matter() -> None:
    world = bootstrap_genesis(seed=99, grid_width=32, grid_height=24, settler_count=4)
    acquirer, target = _pick_two_settlers(world)

    plot_id = next(pid for pid, pl in world.plots.items() if pl.owner is None)
    world.plots[plot_id].owner = target
    register_placed_building(
        world,
        PlacedBuilding(
            instance_id="b-test-1",
            blueprint_id="foundry",
            plot_id=str(plot_id),
            grid_x=0,
            grid_y=0,
            built_at_tick=0,
            built_by=str(target),
            status="operational",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=9999,
            book_value_cents=50_000,
        ),
    )
    world.inventory.add(target, MaterialId("coal"), 12)
    _seed_settler_cash(world, acquirer, 500_000)
    _seed_settler_cash(world, target, 10_000)
    snap = ConservationSnapshot.of(world.ledger, world.inventory)

    liq = liquidation_value_cents(world, target)
    assert liq >= 50_000

    result = execute_buyout(world, acquirer, target)
    assert result["ok"], result
    assert target not in world.parties
    assert world.plots[plot_id].owner == acquirer
    assert world.inventory.qty(acquirer, MaterialId("coal")) >= 12

    assert_money_conserved(world.ledger, snap.ledger_total_cents)
    assert_matter_conserved(world.inventory, snap.inventory_total_units)


def test_liquidation_value_includes_claim_and_buildings() -> None:
    world = bootstrap_genesis(seed=7, grid_width=16, grid_height=16, settler_count=2)
    _, target = _pick_two_settlers(world)
    plot_id = PlotId(next(iter(world.plots)))
    world.plots[plot_id].owner = target
    claim = int(claim_cost_cents_for_plot(world, plot_id))
    register_placed_building(
        world,
        PlacedBuilding(
            instance_id="b-test-2",
            blueprint_id="power_shed",
            plot_id=str(plot_id),
            grid_x=1,
            grid_y=1,
            built_at_tick=0,
            built_by=str(target),
            status="operational",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=9999,
            book_value_cents=25_000,
        ),
    )
    val = liquidation_value_cents(world, target)
    assert val >= claim + 25_000

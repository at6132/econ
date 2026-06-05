"""Deal-making — bilateral contracts, loans, and market tactics conserve money."""

from __future__ import annotations

from realm.agents.settler_identity import assign_settler_personality
from realm.core.conservation import (
    ConservationSnapshot,
    assert_money_conserved,
    assert_matter_conserved,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.deals.bank_loans import (
    GENESIS_BANK_PARTY_ID,
    GENESIS_BANK_STARTING_CASH_CENTS,
    request_loan,
    seed_genesis_bank,
    tick_loan_repayment,
)
from realm.deals.bilateral_contracts import (
    BilateralContract,
    _contract_to_dict,
    propose_bilateral_contract,
    tick_bilateral_contracts,
)
from realm.economy.markets import place_sell_order
from realm.infrastructure.plot_logistics import add_party_plot_stock
from realm.world import bootstrap_genesis


def _settlers(world, n: int = 2) -> list[PartyId]:
    return sorted(
        (p for p in world.parties if str(p).startswith("settler_")),
        key=str,
    )[:n]


def _seed_cash(world, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    world.ledger.ensure_account(acct)
    world.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=cents)


def test_genesis_bank_seeded_at_bootstrap() -> None:
    world = bootstrap_genesis(seed=11, grid_width=12, grid_height=10, settler_count=2)
    assert GENESIS_BANK_PARTY_ID in world.parties
    assert (
        world.ledger.balance(party_cash_account(GENESIS_BANK_PARTY_ID))
        == GENESIS_BANK_STARTING_CASH_CENTS
    )


def test_bilateral_contract_fulfillment_conserves_money_and_matter() -> None:
    world = bootstrap_genesis(seed=21, grid_width=12, grid_height=10, settler_count=2)
    seller, buyer = _settlers(world)
    _seed_cash(world, buyer, 500_000)

    material = MaterialId("coal")
    add_party_plot_stock(world, seller, material, 30)

    world.tick = 7 * 1440
    contract = BilateralContract(
        contract_id="bc-test-1",
        seller_party=seller,
        buyer_party=buyer,
        material_id=material,
        qty_per_week=5,
        price_cents_per_unit=100,
        duration_weeks=4,
        created_tick=int(world.tick),
    )
    world.scenario_state["bilateral_contracts"] = [_contract_to_dict(contract)]

    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    tick_bilateral_contracts(world)
    assert_money_conserved(world.ledger, snap.ledger_total_cents)
    assert_matter_conserved(world.inventory, snap.inventory_total_units)


def test_propose_bilateral_contract_can_succeed() -> None:
    world = bootstrap_genesis(seed=55, grid_width=12, grid_height=10, settler_count=2)
    seller, buyer = _settlers(world)
    assign_settler_personality(world, seller)
    assign_settler_personality(world, buyer)
    store = world.scenario_state.setdefault("settler_identities", {})
    store[str(buyer)]["personality"]["risk_tolerance"] = 0.99

    material = MaterialId("coal")
    accepted = False
    for tick in range(1, 40):
        world.tick = tick
        result = propose_bilateral_contract(
            world,
            seller,
            buyer,
            material,
            qty_per_week=5,
            price_cents_per_unit=1,
            duration_weeks=4,
            exclusive=False,
        )
        if result.get("ok"):
            accepted = True
            break
    assert accepted


def test_bank_loan_conserves_money() -> None:
    world = bootstrap_genesis(seed=31, grid_width=12, grid_height=10, settler_count=2)
    borrower = _settlers(world)[0]
    snap = ConservationSnapshot.of(world.ledger, world.inventory)

    result = request_loan(world, borrower, 100_000)
    assert result["ok"], result
    assert_money_conserved(world.ledger, snap.ledger_total_cents)

    world.tick = 7 * TICKS_PER_GAME_DAY
    tick_loan_repayment(world)
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_cornering_buys_thin_book() -> None:
    world = bootstrap_genesis(seed=41, grid_width=12, grid_height=10, settler_count=24)
    from realm.agents.settler_identity import _party_hash
    from realm.deals.market_tactics import tick_market_cornering

    week = 7 * TICKS_PER_GAME_DAY
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    cornerer = next(p for p in settlers if _party_hash(p) % week == 0)
    store = world.scenario_state.setdefault("settler_identities", {})
    store.setdefault(str(cornerer), {})["personality"] = {
        "risk_tolerance": 0.5,
        "specialization_loyalty": 0.5,
        "social_radius": 3,
        "patience": 0.5,
        "greed_index": 0.9,
    }
    _seed_cash(world, cornerer, 1_000_000)

    material = MaterialId("mining_pick")
    world.market_asks_by_material.pop(str(material), None)
    seller = PartyId("player")
    world.inventory.add(seller, material, 15)
    listed = place_sell_order(world, seller, material, 10, 500)
    assert listed.get("ok"), listed

    world.tick = week
    tick_market_cornering(world)
    corners = world.scenario_state.get("market_corners") or []
    assert any(
        isinstance(c, dict) and c.get("status") == "active" and c.get("party") == str(cornerer)
        for c in corners
    )

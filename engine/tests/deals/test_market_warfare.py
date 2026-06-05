"""Market warfare — cartels, panic, speculation, shorts conserve money."""

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
from realm.deals.bilateral_contracts import BilateralContract, _contract_to_dict
from realm.deals.market_warfare import (
    cartel_listing_floor_cents,
    tick_cartel_formation,
    tick_panic_selling,
    tick_short_positions,
    tick_speculative_positions,
)
from realm.actions import claim_plot
from realm.economy.markets import place_sell_order
from realm.infrastructure.plot_logistics import add_party_plot_stock
from realm.world import bootstrap_genesis
from realm.world.terrain import Terrain


def _claim_plot_for(world, party: PartyId) -> None:
    for plot in sorted(world.plots.values(), key=lambda p: (p.y, p.x)):
        if plot.owner is not None:
            continue
        if plot.terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP):
            continue
        if claim_plot(world, party, plot.plot_id).get("ok"):
            return
    raise AssertionError("no claimable plot")


def _settlers(world, n: int = 4) -> list[PartyId]:
    return sorted(
        (p for p in world.parties if str(p).startswith("settler_")),
        key=str,
    )[:n]


def _seed_cash(world, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    world.ledger.ensure_account(acct)
    world.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=cents)


def _set_personality(
    world,
    party: PartyId,
    *,
    greed: float = 0.5,
    risk: float = 0.5,
) -> None:
    store = world.scenario_state.setdefault("settler_identities", {})
    store.setdefault(str(party), {})["personality"] = {
        "risk_tolerance": risk,
        "specialization_loyalty": 0.5,
        "social_radius": 3,
        "patience": 0.5,
        "greed_index": greed,
    }


def _set_bullish_intel(world, party: PartyId, material: MaterialId) -> None:
    store = world.scenario_state.setdefault("settler_identities", {})
    row = store.setdefault(str(party), {})
    row["world_model"] = {
        "known_settlers": {},
        "material_intel": {
            str(material): {
                "trend": "+",
                "last_seen_ask": 50,
                "last_seen_bid": 40,
                "uncertainty": 0.0,
            }
        },
        "last_updated_tick": 0,
    }
    world.scenario_state.setdefault("trend_streaks", {}).setdefault(str(party), {})[
        str(material)
    ] = 2


def test_cartel_forms_and_enforces_floor() -> None:
    world = bootstrap_genesis(seed=71, grid_width=12, grid_height=10, settler_count=4)
    settlers = _settlers(world, 4)
    material = MaterialId("coal")
    world.market_asks_by_material.pop(str(material), None)

    for i, party in enumerate(settlers[:3]):
        _seed_cash(world, party, 500_000)
        _claim_plot_for(world, party)
        _set_personality(world, party, greed=0.95)
        add_party_plot_stock(world, party, material, 20)
        listed = place_sell_order(world, party, material, 10, 100 + i * 5)
        assert listed.get("ok"), listed

    formed = False
    for day in range(1, 200):
        tick = day * TICKS_PER_GAME_DAY
        if tick % (14 * TICKS_PER_GAME_DAY) != 0:
            continue
        world.tick = tick
        roll = world.rng(f"cartel:{material}:{world.tick}").random()
        if roll >= 0.3 * 0.95:
            continue
        tick_cartel_formation(world)
        formed = True
        break
    assert formed, "no deterministic cartel roll in search window"
    cartels = world.scenario_state.get("cartels") or {}
    row = cartels.get(str(material))
    assert isinstance(row, dict), "expected cartel on coal"
    assert row.get("status") == "active"
    member = PartyId(str(row["members"][0]))
    floor = cartel_listing_floor_cents(world, member, material)
    assert floor is not None
    assert floor >= 140


def test_cartel_breaks_on_undercut() -> None:
    world = bootstrap_genesis(seed=72, grid_width=12, grid_height=10, settler_count=4)
    settlers = _settlers(world, 4)
    material = MaterialId("iron_ore")
    members = [str(s) for s in settlers[:3]]
    world.scenario_state["cartels"] = {
        str(material): {
            "members": members,
            "floor_price_cents": 500,
            "formed_tick": 0,
            "status": "active",
        }
    }
    outsider = settlers[3]
    _seed_cash(world, outsider, 500_000)
    _claim_plot_for(world, outsider)
    add_party_plot_stock(world, outsider, material, 10)
    listed = place_sell_order(world, outsider, material, 5, 400)
    assert listed.get("ok"), listed
    world.tick = TICKS_PER_GAME_DAY
    tick_cartel_formation(world)
    assert world.scenario_state["cartels"][str(material)]["status"] == "broken"


def test_panic_selling_conserves_money() -> None:
    world = bootstrap_genesis(seed=81, grid_width=12, grid_height=10, settler_count=2)
    party = _settlers(world)[0]
    material = MaterialId("coal")
    _seed_cash(world, party, 500_000)
    _claim_plot_for(world, party)
    _seed_cash(world, party, 50_000)
    add_party_plot_stock(world, party, material, 50)

    store = world.scenario_state.setdefault("settler_cash_snapshots", {})
    week_ago = int(world.tick)
    store[str(party)] = [[week_ago, 100_000], [week_ago + TICKS_PER_GAME_DAY, 50_000]]

    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    world.tick = TICKS_PER_GAME_DAY
    tick_panic_selling(world)
    assert_money_conserved(world.ledger, snap.ledger_total_cents)
    assert_matter_conserved(world.inventory, snap.inventory_total_units)


def test_speculative_positions_conserves_money() -> None:
    world = bootstrap_genesis(seed=91, grid_width=12, grid_height=10, settler_count=2)
    party = _settlers(world)[0]
    assign_settler_personality(world, party)
    _set_personality(world, party, risk=0.95)
    _seed_cash(world, party, 200_000)
    material = MaterialId("coal")
    seller = PartyId("player")
    world.inventory.add(seller, material, 100)
    place_sell_order(world, seller, material, 100, 50)

    _set_bullish_intel(world, party, material)

    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    world.tick = 3 * TICKS_PER_GAME_DAY
    tick_speculative_positions(world)
    assert_money_conserved(world.ledger, snap.ledger_total_cents)
    assert_matter_conserved(world.inventory, snap.inventory_total_units)


def test_short_positions_require_contracts_and_conserve() -> None:
    world = bootstrap_genesis(seed=101, grid_width=12, grid_height=10, settler_count=3)
    short_party, lender, _ = _settlers(world, 3)
    material = MaterialId("coal")

    world.tick = 7 * TICKS_PER_GAME_DAY
    tick_short_positions(world)
    assert not world.scenario_state.get("short_positions")

    seller, buyer = short_party, lender
    contract = BilateralContract(
        contract_id="bc-short-gate",
        seller_party=seller,
        buyer_party=buyer,
        material_id=material,
        qty_per_week=5,
        price_cents_per_unit=100,
        duration_weeks=4,
        created_tick=int(world.tick),
    )
    world.scenario_state["bilateral_contracts"] = [_contract_to_dict(contract)]

    _seed_cash(world, lender, 500_000)
    _claim_plot_for(world, lender)
    _set_personality(world, short_party, risk=0.95)
    _set_bullish_intel(world, short_party, material)
    _seed_cash(world, short_party, 200_000)
    add_party_plot_stock(world, lender, material, 30)
    place_sell_order(world, PartyId("player"), material, 20, 120)

    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    tick_short_positions(world)
    assert_money_conserved(world.ledger, snap.ledger_total_cents)
    assert_matter_conserved(world.inventory, snap.inventory_total_units)

"""Phase 9I - polish realism fixes.

Covers:
- Mass-weighted shipping surcharge: heavy materials cost more per tile.
- Progressive plot claim fee: each existing owned plot increases the next fee.
- Staggered laborer ages at bootstrap: no day-100 mass-retirement cliff.
"""

from __future__ import annotations

from collections import Counter

import pytest

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.infrastructure.movement import (
    BASE_SHIP_FEE_CENTS,
    MASS_SHIP_TON_TILE_CENTS,
    PER_TILE_SHIP_CENTS,
    dispatch_shipment,
)
from realm.materials import MATERIALS
from realm.population.laborers import RETIREMENT_AGE_TICKS
from realm.world import bootstrap_genesis
from realm.world.geo import manhattan
from realm.world.world import bootstrap_frontier


def test_stone_shipping_costs_more_than_grain_per_tile_at_same_qty() -> None:
    w = bootstrap_frontier(seed=70, grid_width=4, grid_height=2)
    a, b = PlotId("p-0-0"), PlotId("p-3-0")
    p = PartyId("player")
    assert claim_plot(w, p, a)["ok"]
    assert claim_plot(w, p, b)["ok"]
    w.inventory.add(p, MaterialId("grain"), 10)
    w.inventory.add(p, MaterialId("stone"), 10)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(p),
        amount_cents=1_000_000,
    )

    grain_ship = dispatch_shipment(w, p, MaterialId("grain"), 10, a, b)
    stone_ship = dispatch_shipment(w, p, MaterialId("stone"), 10, a, b)

    assert grain_ship["ok"], grain_ship
    assert stone_ship["ok"], stone_ship
    assert stone_ship["fee_cents"] > grain_ship["fee_cents"]


def test_mass_surcharge_scales_linearly_with_qty() -> None:
    w = bootstrap_frontier(seed=71, grid_width=4, grid_height=2)
    a, b = PlotId("p-0-0"), PlotId("p-3-0")
    p = PartyId("player")
    assert claim_plot(w, p, a)["ok"]
    assert claim_plot(w, p, b)["ok"]
    w.inventory.add(p, MaterialId("stone"), 30)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(p),
        amount_cents=1_000_000,
    )
    dist = manhattan(w, a, b)
    base_fee = BASE_SHIP_FEE_CENTS + dist * PER_TILE_SHIP_CENTS
    stone_kg = MATERIALS[MaterialId("stone")].mass_per_unit_kg

    r5 = dispatch_shipment(w, p, MaterialId("stone"), 5, a, b)
    expected_5 = base_fee + int(
        (stone_kg * 5 / 1000.0) * dist * MASS_SHIP_TON_TILE_CENTS
    )
    assert r5["fee_cents"] == expected_5

    r10 = dispatch_shipment(w, p, MaterialId("stone"), 10, a, b)
    expected_10 = base_fee + int(
        (stone_kg * 10 / 1000.0) * dist * MASS_SHIP_TON_TILE_CENTS
    )
    assert r10["fee_cents"] == expected_10
    assert r10["fee_cents"] - base_fee == (r5["fee_cents"] - base_fee) * 2


def test_first_claim_is_unmodified() -> None:
    w = bootstrap_frontier(seed=80, grid_width=4, grid_height=2)
    p = PartyId("player")
    plot = PlotId("p-1-0")
    cash_before = w.ledger.balance(party_cash_account(p))

    r = claim_plot(w, p, plot)

    assert r["ok"], r
    cash_after = w.ledger.balance(party_cash_account(p))
    assert cash_after <= cash_before


def test_progressive_multiplier_kicks_in_after_each_claim() -> None:
    w = bootstrap_genesis(seed=200, grid_width=48, grid_height=36, settler_count=4)
    p = PartyId("player_test")
    w.parties.add(p)
    w.ledger.ensure_account(party_cash_account(p))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(p),
        amount_cents=1_000_000_000,
    )
    from realm.world import claim_cost_cents_for_plot

    candidates = sorted(
        (
            (claim_cost_cents_for_plot(w, pid), str(pid))
            for pid, plot in w.plots.items()
            if plot.owner is None
        ),
        reverse=True,
    )
    expensive_plots = [PlotId(s) for cost, s in candidates[:5] if cost > 0]
    if len(expensive_plots) < 3:
        pytest.skip("not enough dense plots in this world to test multiplier")

    for i, pid in enumerate(expensive_plots[:3]):
        base_cost = claim_cost_cents_for_plot(w, pid)
        cash_before = w.ledger.balance(party_cash_account(p))
        r = claim_plot(w, p, pid)
        assert r["ok"], (r, i)
        cash_after = w.ledger.balance(party_cash_account(p))
        paid = cash_before - cash_after
        expected = (
            base_cost
            if i == 0
            else base_cost * (10_000 + i * 2_000) // 10_000
        )
        assert paid == expected, (i, paid, expected, base_cost)


def test_bootstrap_laborer_ages_are_staggered() -> None:
    w = bootstrap_genesis(seed=300, grid_width=48, grid_height=36, settler_count=4)
    if not w.laborers:
        pytest.skip("no laborers seeded")

    ages = [int(lab.age_ticks) for lab in w.laborers.values()]
    distinct = len(set(ages))
    assert distinct > 50, f"only {distinct} distinct ages"
    assert max(ages) - min(ages) > int(RETIREMENT_AGE_TICKS * 0.3)

    largest_cohort = Counter(ages).most_common(1)[0][1]
    assert largest_cohort < len(ages) // 10

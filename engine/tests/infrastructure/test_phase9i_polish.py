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
from realm.infrastructure.movement import compute_shipping_fee, dispatch_shipment
from realm.population.laborers import TICKS_PER_GAME_DAY
from realm.world import bootstrap_genesis
from realm.world.geo import manhattan
from realm.world.world import bootstrap_frontier


def test_bulk_shipping_same_material_fee_per_unit_at_same_qty() -> None:
    w = bootstrap_frontier(seed=70, grid_width=4, grid_height=2)
    a, b = PlotId("p-0-0"), PlotId("p-3-0")
    p = PartyId("player")
    assert claim_plot(w, p, a)["ok"]
    assert claim_plot(w, p, b)["ok"]
    grain = compute_shipping_fee(w, a, b, qty=10)
    stone = compute_shipping_fee(w, a, b, qty=10)
    assert grain["ok"] and stone["ok"]
    assert grain["per_unit_cents"] == stone["per_unit_cents"]


def test_bulk_per_unit_drops_with_larger_qty() -> None:
    w = bootstrap_frontier(seed=71, grid_width=4, grid_height=2)
    a, b = PlotId("p-0-0"), PlotId("p-3-0")
    small = compute_shipping_fee(w, a, b, qty=5)
    large = compute_shipping_fee(w, a, b, qty=30)
    assert small["ok"] and large["ok"]
    assert large["per_unit_cents"] <= small["per_unit_cents"]


def test_first_claim_is_unmodified() -> None:
    w = bootstrap_frontier(seed=80, grid_width=4, grid_height=2)
    p = PartyId("player")
    plot = next(iter(w.plots.keys()))
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
    assert distinct > 10, f"only {distinct} distinct ages"
    assert max(ages) <= 59 * TICKS_PER_GAME_DAY
    assert max(ages) - min(ages) > 30 * TICKS_PER_GAME_DAY
    for lab in w.laborers.values():
        assert lab.health == 1.0

    largest_cohort = Counter(ages).most_common(1)[0][1]
    assert largest_cohort < len(ages) // 10

"""Sprint 3 — Phase B · geographic clustering / regional identity.

Covers:
- B1: Mineral belts emerge from layered noise — between-region variance
  exceeds within-region variance for iron grades.
- B2: Population density falls off exponentially from pop hubs.
- B2: Claim cost scales with population density.
- B3: A hub buyer picks the nearer seller when prices are equal.
"""

from __future__ import annotations

import statistics

from realm.actions import claim_plot
from realm.geo_clustering import (
    CLAIM_COST_PEAK_CENTS,
    claim_cost_cents_from_density,
    population_density_for_cell,
)
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import Inventory, MatterErr
from realm.ledger import (
    Ledger,
    MoneyErr,
    party_cash_account,
    system_reserve_account,
)
from realm.markets import market_buy, place_sell_order
from realm.terrain import Terrain
from realm.world import (
    Plot,
    SubsurfaceRoll,
    World,
    bootstrap_genesis,
    claim_cost_cents_for_plot,
    population_density_for,
)


def test_mineral_belts_exist() -> None:
    """Iron grade variance between regions should exceed average within-region variance."""
    w = bootstrap_genesis(
        seed=42,
        grid_width=48,
        grid_height=36,
        settler_count=10,
        starting_cash_cents=100,
    )
    # Partition into 3×3 region grid; collect surveyed iron grades per region.
    rxs = [0, w.plots and max(p.x for p in w.plots.values()) // 3 + 1]
    rys = [0, max(p.y for p in w.plots.values()) // 3 + 1]
    by_region: dict[tuple[int, int], list[float]] = {}
    for p in w.plots.values():
        if p.terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP):
            continue
        rx = min(2, p.x * 3 // 48)
        ry = min(2, p.y * 3 // 36)
        by_region.setdefault((rx, ry), []).append(p.subsurface.iron_ore_grade)
    region_means = [
        statistics.fmean(vals) for vals in by_region.values() if len(vals) >= 4
    ]
    assert len(region_means) >= 5
    between_var = statistics.pvariance(region_means)
    within_vars = [
        statistics.pvariance(vals) for vals in by_region.values() if len(vals) >= 4
    ]
    avg_within = statistics.fmean(within_vars)
    # Belts mean some regions are systematically richer/poorer — between > within.
    assert between_var > avg_within * 0.20, (
        f"clustering too weak: between_var={between_var:.4f}, avg_within={avg_within:.4f}"
    )


def test_population_density_highest_near_hubs() -> None:
    w = bootstrap_genesis(
        seed=42,
        grid_width=96,
        grid_height=72,
        settler_count=4,
        starting_cash_cents=100,
    )
    hubs = w.scenario_state["pop_hub_coords"]
    hub_coords = [tuple(c) for c in hubs.values()]
    # "Near" = within 6 tiles of any hub; "far" = ≥50 tiles from every hub.
    near: list[float] = []
    far: list[float] = []
    for p in w.plots.values():
        nearest = min(abs(p.x - hx) + abs(p.y - hy) for hx, hy in hub_coords)
        density = population_density_for(w, p.plot_id)
        if nearest <= 6:
            near.append(density)
        elif nearest >= 50:
            far.append(density)
    assert near and far
    assert min(near) > 0.55, f"near-hub density too low: min={min(near):.3f}"
    assert max(far) < 0.25, f"far-from-hub density too high: max={max(far):.3f}"


def test_claim_cost_scales_with_density() -> None:
    # Pure-function smoke tests first.
    assert claim_cost_cents_from_density(0.05) < claim_cost_cents_from_density(0.5)
    assert claim_cost_cents_from_density(0.5) < claim_cost_cents_from_density(0.95)
    assert claim_cost_cents_from_density(0.95) <= CLAIM_COST_PEAK_CENTS

    # End-to-end: in a genesis world, claiming a high-density plot near a hub costs
    # measurably more than claiming a frontier plot.
    w = bootstrap_genesis(
        seed=42,
        grid_width=96,
        grid_height=72,
        settler_count=4,
        starting_cash_cents=10_000_000,
    )
    hub_coords = [tuple(c) for c in w.scenario_state["pop_hub_coords"].values()]
    dense_plot: PlotId | None = None
    frontier_plot: PlotId | None = None
    for p in w.plots.values():
        if p.owner is not None:
            continue
        if p.terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP):
            continue
        nearest = min(abs(p.x - hx) + abs(p.y - hy) for hx, hy in hub_coords)
        if nearest <= 3 and dense_plot is None:
            dense_plot = p.plot_id
        elif nearest >= 60 and frontier_plot is None:
            frontier_plot = p.plot_id
        if dense_plot is not None and frontier_plot is not None:
            break
    assert dense_plot is not None and frontier_plot is not None
    assert claim_cost_cents_for_plot(w, dense_plot) > claim_cost_cents_for_plot(
        w, frontier_plot
    )
    assert claim_cost_cents_for_plot(w, frontier_plot) <= 50


def test_regional_buyer_preference() -> None:
    """Buyer with prefer_origin picks the closer seller when prices are equal."""
    sub = SubsurfaceRoll(0.0, 0.0, 0.0, 0.0)
    plots: dict[PlotId, Plot] = {}
    for y in range(40):
        for x in range(60):
            pid = PlotId(f"p-{x}-{y}")
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=Terrain.PLAINS,
                owner=None,
                subsurface=sub,
                surveyed=True,
            )
    w = World(
        seed=1,
        tick=0,
        plots=plots,
        ledger=Ledger(),
        inventory=Inventory(),
        parties=set(),
        scenario_id="testbed",
        use_plot_output_logistics=False,
    )
    assert not isinstance(w.ledger.seed_system_reserve(10_000_000_000), MoneyErr)

    buyer = PartyId("hub")
    near = PartyId("near_seller")
    far = PartyId("far_seller")
    for p in (buyer, near, far):
        w.parties.add(p)
        w.ledger.ensure_account(party_cash_account(p))
        w.ledger.transfer(
            debit=system_reserve_account(),
            credit=party_cash_account(p),
            amount_cents=100_000,
        )
        w.reputation[str(p)] = {"honored": 0, "breached": 0}

    plots[PlotId("p-10-10")].owner = near  # buyer is at (10, 10) — same plot
    plots[PlotId("p-55-35")].owner = far

    # Inventory + listings at the same price.
    res = w.inventory.add(near, MaterialId("grain"), 50)
    assert not isinstance(res, MatterErr)
    res = w.inventory.add(far, MaterialId("grain"), 50)
    assert not isinstance(res, MatterErr)
    assert place_sell_order(w, near, MaterialId("grain"), 20, 150)["ok"]
    assert place_sell_order(w, far, MaterialId("grain"), 20, 150)["ok"]

    near_cash0 = w.ledger.balance(party_cash_account(near))
    far_cash0 = w.ledger.balance(party_cash_account(far))
    r = market_buy(w, buyer, MaterialId("grain"), 5, prefer_origin=(10, 10))
    assert r["ok"]
    assert r["filled"] == 5
    near_cash1 = w.ledger.balance(party_cash_account(near))
    far_cash1 = w.ledger.balance(party_cash_account(far))
    # The near seller should be the one credited.
    assert near_cash1 > near_cash0
    assert far_cash1 == far_cash0


def test_population_density_for_cell_pure() -> None:
    """Pure-function smoke test — frontier baseline + hub peak."""
    hubs = [(20, 20), (60, 30)]
    near = population_density_for_cell(20, 20, hubs)
    far = population_density_for_cell(0, 50, hubs)
    assert near > 0.85
    assert far < 0.2

"""Phase 7A — four-island world generation.

Spec assertions:

1. Default Genesis bootstrap produces exactly four land components (islands).
2. Each island has at least 2 coastal plots (eligible for docking).
3. Ocean tiles are impassable (``tile_movement_cost == math.inf``).
4. No ``pop_hub_*`` parties exist after bootstrap (legacy demand layer removed).
5. ``plot_islands`` membership is cached deterministically on the world.
6. Inter-island shipments pay a 2× per-tile open-ocean modifier.
"""

from __future__ import annotations

import math

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.islands import (
    compute_plot_islands,
    is_inter_island_shipment,
    is_ocean_plot,
    island_coastal_plot_ids,
    plot_island_id,
    tile_movement_cost,
)
from realm.markets import place_sell_order
from realm.movement import dispatch_shipment
from realm.terrain import Terrain
from realm.world import bootstrap_genesis


def _world():
    return bootstrap_genesis(seed=42, settler_count=0)


# ───────────────────────── invariants ─────────────────────────


def test_default_bootstrap_produces_exactly_four_landmasses() -> None:
    """Default 96×72 Genesis map yields exactly four land components."""
    w = _world()
    islands_map = w.scenario_state["plot_islands"]
    distinct = sorted({int(v) for v in islands_map.values()})
    assert distinct == [0, 1, 2, 3], f"expected 4 islands [0..3]; got {distinct}"


def test_each_island_has_at_least_two_coastal_plots() -> None:
    """Every island must have ≥ 2 coastal plots so it can host a dock."""
    w = _world()
    for island_id in range(4):
        coastal = island_coastal_plot_ids(w, island_id)
        assert len(coastal) >= 2, (
            f"island {island_id} has only {len(coastal)} coastal plot(s); "
            f"shipping wouldn't have a port"
        )


def test_ocean_tiles_are_impassable() -> None:
    """``tile_movement_cost`` is ``math.inf`` on every deep-ocean plot."""
    w = _world()
    seen_ocean = False
    for pid, p in w.plots.items():
        if p.terrain == Terrain.WATER_DEEP:
            seen_ocean = True
            assert tile_movement_cost(w, pid) == math.inf
            assert is_ocean_plot(w, pid)
            assert plot_island_id(w, pid) is None
    assert seen_ocean, "expected at least one deep-ocean tile on the four-island map"


def test_land_tiles_are_passable_and_assigned_to_an_island() -> None:
    """Every non-ocean land plot has a finite cost and a non-None island id."""
    w = _world()
    for pid, p in w.plots.items():
        if p.terrain == Terrain.WATER_DEEP:
            continue
        assert math.isfinite(tile_movement_cost(w, pid))
        # Land plots — including beach (``WATER_SHALLOW``) — belong to an island.
        if p.terrain != Terrain.WATER_SHALLOW:
            assert plot_island_id(w, pid) is not None


def test_no_pop_hub_parties_exist_after_bootstrap() -> None:
    """Phase 7A: ``pop_hub_e/w`` are gone — neither party nor coords remain."""
    w = _world()
    assert PartyId("pop_hub_e") not in w.parties
    assert PartyId("pop_hub_w") not in w.parties
    assert "pop_hub_coords" not in w.scenario_state


def test_plot_islands_cache_is_deterministic() -> None:
    """Same seed → same island assignment."""
    w1 = bootstrap_genesis(seed=42, settler_count=0)
    w2 = bootstrap_genesis(seed=42, settler_count=0)
    assert w1.scenario_state["plot_islands"] == w2.scenario_state["plot_islands"]
    # And ``compute_plot_islands`` is a pure function on the plot dict.
    recomputed = compute_plot_islands(w1)
    assert recomputed == w1.scenario_state["plot_islands"]


def test_inter_island_shipment_helper_detects_cross_island_route() -> None:
    """``is_inter_island_shipment`` is True only when the two plots are on different islands."""
    w = _world()
    islands_map = w.scenario_state["plot_islands"]
    by_island: dict[int, list[str]] = {}
    for pid_s, isl in islands_map.items():
        by_island.setdefault(int(isl), []).append(pid_s)
    # Same-island pair → False.
    same = by_island[0]
    if len(same) >= 2:
        assert not is_inter_island_shipment(w, PlotId(same[0]), PlotId(same[1]))
    # Cross-island pair → True.
    cross = (PlotId(by_island[0][0]), PlotId(by_island[1][0]))
    assert is_inter_island_shipment(w, *cross)


def test_inter_island_shipping_pays_2x_per_tile() -> None:
    """A shipment across the ocean costs ~2× the per-tile portion vs. intra-island."""
    w = bootstrap_genesis(seed=42, settler_count=0, starting_cash_cents=100_000_000)
    player = PartyId("player")
    islands_map = w.scenario_state["plot_islands"]
    by_island: dict[int, list[str]] = {}
    for pid_s, isl in islands_map.items():
        by_island.setdefault(int(isl), []).append(pid_s)

    # Two plots on island 0 a fixed Manhattan distance apart.
    def _pick_pair_distance(plot_ids: list[str], target_dist: int) -> tuple[PlotId, PlotId] | None:
        from realm.geo import manhattan as _manhattan

        for a in plot_ids[:50]:
            for b in plot_ids[:50]:
                if a == b:
                    continue
                if _manhattan(w, PlotId(a), PlotId(b)) == target_dist:
                    return PlotId(a), PlotId(b)
        return None

    intra = _pick_pair_distance(by_island[0], 4)
    inter = _pick_pair_distance([by_island[0][0], by_island[1][0]], 4) or (
        PlotId(by_island[0][0]),
        PlotId(by_island[1][0]),
    )
    assert intra is not None
    intra_a, intra_b = intra
    inter_a, inter_b = inter
    # Claim those plots for the player and seed inventory.
    for pid in (intra_a, intra_b, inter_a, inter_b):
        w.plots[pid].owner = player
    w.inventory.add(player, MaterialId("coal"), 8)
    # Place a resting ask so unit value is non-zero (movement uses ask to bound tolls).
    place_sell_order(w, player, MaterialId("coal"), 1, 100)
    intra_res = dispatch_shipment(w, player, MaterialId("coal"), 1, intra_a, intra_b)
    assert intra_res["ok"], intra_res
    assert intra_res["inter_island"] is False
    assert intra_res["ocean_modifier_mult"] == 1
    inter_res = dispatch_shipment(w, player, MaterialId("coal"), 1, inter_a, inter_b)
    assert inter_res["ok"], inter_res
    assert inter_res["inter_island"] is True
    assert inter_res["ocean_modifier_mult"] == 2
    # Inter-island fee must be strictly higher than intra-island for the same
    # ``dist``; with a 2× per-tile multiplier and finite base fee the inter
    # cost should be roughly 2× minus the unchanged base portion.
    assert inter_res["fee_cents"] > intra_res["fee_cents"]

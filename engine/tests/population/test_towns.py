"""Phase 7C — Town detection, residential housing, capacity, naming."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.production.buildings import BUILDINGS, build_on_plot
from realm.core.ids import PartyId, PlotId
from realm.world.terrain import Terrain
from realm.population.towns import (
    RESIDENCE_BUILDING_ID,
    SETTLEMENT_PARTY_ID,
    STARTING_RESIDENCES_PER_ISLAND,
    starting_residence_plot_count_for_island,
    TOWN_MIN_RESIDENCES,
    TOWN_PROXIMITY_TILES,
    Town,
    _generate_town_name,
    assign_laborer_residence,
    detect_towns,
    on_residence_built,
    residence_capacity,
    residence_occupancy,
    town_for_plot,
)
from realm.world import bootstrap_genesis
from turnkey_fixtures import grant_turnkey_self_materials


# ───────────────────────── bootstrap towns ─────────────────────────


def test_genesis_bootstrap_seeds_one_town_per_island():
    """A four-island world has exactly one starting town per island."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    plot_islands = w.scenario_state.get("plot_islands", {})
    distinct_islands = sorted({int(v) for v in plot_islands.values()})
    assert len(distinct_islands) == 4
    assert len(w.towns) == 4
    by_island = {t.island_id for t in w.towns.values()}
    assert by_island == set(distinct_islands)


def test_each_starting_town_has_min_residences_and_a_name():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    for t in w.towns.values():
        assert len(t.residential_plots) >= TOWN_MIN_RESIDENCES
        assert t.name, "town must have a non-empty name"


def test_starting_town_residences_owned_by_settlement_party():
    """Bootstrap residences belong to the synthetic ``genesis_settlement``."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    assert PartyId(SETTLEMENT_PARTY_ID) in w.parties
    for t in w.towns.values():
        for pid in t.residential_plots:
            plot = w.plots[pid]
            assert str(plot.owner) == SETTLEMENT_PARTY_ID


def test_initial_laborers_housed_up_to_capacity():
    """Laborers fill residences up to capacity; surplus stays unhoused."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    cap_per_residence = int(BUILDINGS[RESIDENCE_BUILDING_ID]["capacity"])
    for t in w.towns.values():
        expected = (
            starting_residence_plot_count_for_island(w, t.island_id) * cap_per_residence
        )
        n_in_town = sum(
            1 for lab in w.laborers.values() if lab.home_town == t.town_id
        )
        assert 0 < n_in_town <= expected
        # Shelter need fully restored on housed laborers.
        for lab in w.laborers.values():
            if lab.home_town == t.town_id:
                assert lab.needs["shelter"] == pytest.approx(1.0)


def test_build_and_claim_reject_water_plots() -> None:
    w = bootstrap_genesis(seed=11, grid_width=24, grid_height=20, settler_count=2)
    player = PartyId("player")
    shallow = next(
        pid for pid, p in w.plots.items() if p.terrain == Terrain.WATER_SHALLOW
    )
    w.plots[shallow].owner = None
    assert claim_plot(w, player, shallow)["ok"] is False
    w.plots[shallow].owner = player
    res = build_on_plot(w, player, shallow, RESIDENCE_BUILDING_ID)
    assert res["ok"] is False
    assert "water" in res["reason"].lower()


def test_bootstrap_residences_only_on_dry_land() -> None:
    from realm.production.recipe_sites import plot_allows_structure

    w = bootstrap_genesis(seed=42, grid_width=100, grid_height=100, settler_count=0)
    for b in w.plot_buildings:
        if b.get("building_id") != RESIDENCE_BUILDING_ID:
            continue
        plot = w.plots.get(PlotId(str(b["plot_id"])))
        assert plot is not None
        assert plot_allows_structure(plot), (
            f"residence on {plot.terrain.value} at {b['plot_id']}"
        )


def test_bootstrap_houses_all_default_island_laborers():
    """Residence count scales with landmass-density labor targets per island."""
    w = bootstrap_genesis(
        seed=42, grid_width=64, grid_height=48, settler_count=4, map_layout="continental"
    )
    housed = sum(1 for lab in w.laborers.values() if lab.home_town)
    unhoused = sum(1 for lab in w.laborers.values() if not lab.home_town)
    assert unhoused == 0, f"expected all laborers housed, unhoused={unhoused}"
    assert housed == len(w.laborers)


# ───────────────────────── detect_towns clustering ─────────────────────────


def test_detect_towns_requires_min_residences():
    """Two residences within 5 tiles do NOT form a town."""
    w = bootstrap_genesis(seed=99, grid_width=64, grid_height=48, settler_count=2)
    initial_town_count = len(w.towns)
    # Pick the player and an unowned plot far from existing towns to avoid
    # accidentally extending one. Build 2 residences only.
    player = PartyId("player")
    candidate_plots: list[PlotId] = []
    for p in w.plots.values():
        if p.owner is not None:
            continue
        if p.terrain in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW):
            continue
        # Avoid plots that already belong to an existing town.
        if town_for_plot(w, p.plot_id) is not None:
            continue
        # Avoid adjacency to existing town residences.
        skip = False
        for t in w.towns.values():
            for tp in t.residential_plots:
                tplot = w.plots[tp]
                if max(abs(p.x - tplot.x), abs(p.y - tplot.y)) <= 6:
                    skip = True
                    break
            if skip:
                break
        if skip:
            continue
        candidate_plots.append(p.plot_id)
        if len(candidate_plots) >= 2:
            break
    assert len(candidate_plots) == 2
    # Claim, fund, build two residences.
    from realm.core.ledger import party_cash_account, system_reserve_account
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=1_000_000,
    )
    for pid in candidate_plots:
        assert claim_plot(w, player, pid)["ok"]
    grant_turnkey_self_materials(w, player, "residence", count=2)
    for pid in candidate_plots:
        res = build_on_plot(w, player, pid, "residence", build_mode="turnkey")
        assert res["ok"], res
        # Skip ahead past construction time.
        w.tick = max(int(w.tick), int(res["completes_at_tick"]) + 1)
    # Re-run detection to reflect tick advance.
    detect_towns(w)
    new_towns = [t for t in w.towns.values() if str(player) in {} or True]
    # Only the original 4 bootstrap towns should remain — these two
    # residences are under the 3-residence threshold.
    assert len(w.towns) == initial_town_count


# ───────────────────────── capacity / occupancy ─────────────────────────


def test_residence_capacity_matches_building_spec():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    spec_cap = int(BUILDINGS[RESIDENCE_BUILDING_ID]["capacity"])
    for t in w.towns.values():
        for pid in t.residential_plots:
            assert residence_capacity(w, pid) == spec_cap


def test_assign_laborer_residence_capacity_blocked():
    """Cannot exceed residence capacity."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    # Pick a residence on the first town that's already maxed.
    first_town = next(iter(w.towns.values()))
    pid = first_town.residential_plots[0]
    cap = residence_capacity(w, pid)
    # Force exactly `cap` laborers home there.
    laborers_on_island = [
        lab for lab in w.laborers.values() if lab.island_id == first_town.island_id
    ]
    assert len(laborers_on_island) > cap
    full = laborers_on_island[:cap]
    overflow = laborers_on_island[cap]
    for lab in full:
        lab.home_plot_id = pid
        lab.home_town = first_town.town_id
    # Try to assign one more.
    overflow.home_plot_id = first_town.residential_plots[1] if len(first_town.residential_plots) > 1 else pid
    overflow.home_town = None
    res = assign_laborer_residence(w, overflow.laborer_id, pid)
    assert not res["ok"]
    assert "capacity" in res["reason"].lower()


def test_assign_laborer_residence_restores_shelter():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    # Free one slot on a residence (all laborers are housed at bootstrap now).
    lab = next(iter(w.laborers.values()))
    lab.needs["shelter"] = 0.20
    # Pick a residence on the same island.
    same_island_town = next(t for t in w.towns.values() if t.island_id == lab.island_id)
    pid = same_island_town.residential_plots[0]
    # Empty the residence first.
    for other in w.laborers.values():
        if other.home_plot_id == pid:
            other.home_plot_id = lab.home_plot_id  # type: ignore[assignment]
            other.home_town = None
    res = assign_laborer_residence(w, lab.laborer_id, pid)
    assert res["ok"], res
    assert lab.needs["shelter"] == pytest.approx(1.0)
    assert lab.home_town == same_island_town.town_id


# ───────────────────────── naming ─────────────────────────


def test_town_name_deterministic_per_seed_and_sequence():
    """Same (seed, town_seq) → same name."""
    assert _generate_town_name(42, 1) == _generate_town_name(42, 1)
    # Different seed → different name (with very high probability).
    assert _generate_town_name(42, 1) != _generate_town_name(99, 1)


def test_town_ids_stable_across_redetection():
    """Re-running detect_towns does not rename existing towns."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    first = {tid: t.name for tid, t in w.towns.items()}
    detect_towns(w)
    again = {tid: t.name for tid, t in w.towns.items()}
    assert first == again


# ───────────────────────── event-driven detection ─────────────────────────


def test_building_a_third_residence_creates_a_new_town():
    """Three residences within 5 tiles of one another form a new town
    even when none of the bootstrap towns is involved."""
    w = bootstrap_genesis(seed=2027, grid_width=64, grid_height=48, settler_count=2)
    player = PartyId("player")
    # Fund the player heavily and grant materials for 3 residences.
    from realm.core.ledger import party_cash_account, system_reserve_account
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=2_000_000,
    )
    grant_turnkey_self_materials(w, player, "residence", count=3)
    # Find 3 adjacent unowned land plots far enough from existing towns to
    # avoid merging.
    candidates: list[PlotId] = []
    for p in w.plots.values():
        if p.owner is not None or p.terrain in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW):
            continue
        if town_for_plot(w, p.plot_id) is not None:
            continue
        # Stay away from existing towns.
        skip = False
        for t in w.towns.values():
            for tp in t.residential_plots:
                tplot = w.plots[tp]
                if max(abs(p.x - tplot.x), abs(p.y - tplot.y)) <= 6:
                    skip = True
                    break
            if skip:
                break
        if skip:
            continue
        candidates.append(p.plot_id)
    assert len(candidates) >= 3, "need 3 candidate plots for a new town"
    # Find 3 within proximity of each other.
    cluster: list[PlotId] = [candidates[0]]
    cx, cy = w.plots[candidates[0]].x, w.plots[candidates[0]].y
    for pid in candidates[1:]:
        p = w.plots[pid]
        if max(abs(p.x - cx), abs(p.y - cy)) <= TOWN_PROXIMITY_TILES:
            cluster.append(pid)
        if len(cluster) >= 3:
            break
    assert len(cluster) == 3
    n_before = len(w.towns)
    for pid in cluster:
        assert claim_plot(w, player, pid)["ok"]
    for pid in cluster:
        res = build_on_plot(w, player, pid, "residence", build_mode="turnkey")
        assert res["ok"], res
        w.tick = max(int(w.tick), int(res["completes_at_tick"]) + 1)
    on_residence_built(w, cluster[-1])  # idempotent refresh
    assert len(w.towns) >= n_before + 1

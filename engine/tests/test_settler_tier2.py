"""Settler adaptation to Tier-2 industry — probabilistic discovery, secondary-tier workshops."""

from __future__ import annotations

import random
from unittest.mock import patch

from realm.actions import claim_plot, survey_plot
from realm.agents_genesis_settlers import (
    SETTLER_DISCOVERY_PROB_PER_GAME_DAY,
    _settler_probabilistic_discovery,
)
from realm.assay import ASSAY_MAX_STAGE, get_assay_stage
from realm.buildings import build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import SubsurfaceRoll, bootstrap_genesis
from turnkey_fixtures import grant_turnkey_self_materials


def _seed_settler_with_assay_lab(w, party: PartyId, pid: PlotId, mineral_field: str) -> None:
    """Give the settler a fully built/operational assay_lab on a plot rich in the target mineral."""
    plot = w.plots[pid]
    plot.terrain = Terrain.SWAMP
    base = {
        "iron_ore_grade": 0.0,
        "copper_ore_grade": 0.0,
        "clay_grade": 0.0,
        "coal_grade": 0.0,
    }
    grades = {
        "sulfur_grade": 0.0,
        "saltpeter_grade": 0.0,
        "tin_grade": 0.0,
        "lead_grade": 0.0,
        "phosphate_grade": 0.0,
        "silica_grade": 0.0,
    }
    grades[mineral_field] = 0.75
    plot.subsurface = SubsurfaceRoll(**base, **grades)
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid)["ok"] is True
    cash = party_cash_account(party)
    extra = w.ledger.transfer(
        debit=__import__("realm.ledger", fromlist=["system_reserve_account"]).system_reserve_account(),
        credit=cash,
        amount_cents=300_000,
    )
    assert extra is None or not hasattr(extra, "reason"), extra
    grant_turnkey_self_materials(w, party, "assay_lab")
    r = build_on_plot(w, party, pid, "assay_lab", build_mode="turnkey")
    assert r["ok"] is True, r
    inst = r["instance_id"]
    for b in w.plot_buildings:
        if b.get("instance_id") == inst:
            b["completes_at_tick"] = -1
            break


def test_settler_probabilistic_discovery_advances_stage_on_hit() -> None:
    """When the RNG lands inside the 1%/game-day window, the settler's stage advances exactly once."""
    w = bootstrap_genesis(seed=501, grid_width=10, grid_height=8, settler_count=2)
    settler = next(iter(p for p in w.parties if str(p).startswith("settler_")))
    plot_id = next(pid for pid, pl in w.plots.items() if pl.owner is None and pl.terrain != Terrain.WATER_DEEP and pl.terrain != Terrain.WATER_SHALLOW)
    _seed_settler_with_assay_lab(w, settler, plot_id, "sulfur_grade")
    w.tick = TICKS_PER_GAME_DAY  # align with the game-day boundary the helper checks
    assert get_assay_stage(w, settler, MaterialId("sulfur_ore")) == 0
    with patch("realm.agents_genesis_settlers.world.rng") if False else patch.object(w, "rng") as rng_mock:
        rng_mock.return_value = random.Random()
        rng_mock.return_value.random = lambda: SETTLER_DISCOVERY_PROB_PER_GAME_DAY / 2  # below threshold
        _settler_probabilistic_discovery(w, settler)
    assert get_assay_stage(w, settler, MaterialId("sulfur_ore")) == 1


def test_settler_probabilistic_discovery_no_hit_no_advance() -> None:
    """If the RNG returns ≥ threshold, the stage stays put — deterministic, no luck-creep."""
    w = bootstrap_genesis(seed=502, grid_width=10, grid_height=8, settler_count=2)
    settler = next(iter(p for p in w.parties if str(p).startswith("settler_")))
    plot_id = next(pid for pid, pl in w.plots.items() if pl.owner is None and pl.terrain != Terrain.WATER_DEEP and pl.terrain != Terrain.WATER_SHALLOW)
    _seed_settler_with_assay_lab(w, settler, plot_id, "sulfur_grade")
    w.tick = TICKS_PER_GAME_DAY
    with patch.object(w, "rng") as rng_mock:
        rng_mock.return_value = random.Random()
        rng_mock.return_value.random = lambda: 0.99  # well above threshold
        _settler_probabilistic_discovery(w, settler)
    assert get_assay_stage(w, settler, MaterialId("sulfur_ore")) == 0


def test_settler_probabilistic_discovery_unlocks_recipes_at_stage_three() -> None:
    """Three hits in a row push the settler to stage 3 and unlock the sulfur recipe chain."""
    w = bootstrap_genesis(seed=503, grid_width=10, grid_height=8, settler_count=2)
    settler = next(iter(p for p in w.parties if str(p).startswith("settler_")))
    plot_id = next(pid for pid, pl in w.plots.items() if pl.owner is None and pl.terrain != Terrain.WATER_DEEP and pl.terrain != Terrain.WATER_SHALLOW)
    _seed_settler_with_assay_lab(w, settler, plot_id, "sulfur_grade")
    for i in range(1, 4):
        w.tick = i * TICKS_PER_GAME_DAY
        with patch.object(w, "rng") as rng_mock:
            rng_mock.return_value = random.Random()
            rng_mock.return_value.random = lambda: 0.0
            _settler_probabilistic_discovery(w, settler)
    assert get_assay_stage(w, settler, MaterialId("sulfur_ore")) == ASSAY_MAX_STAGE
    book = w.party_recipe_books.get(str(settler), set())
    assert "mine_sulfur_ore" in book
    assert "make_sulfuric_acid" in book


def test_settler_probabilistic_discovery_requires_lab() -> None:
    """Without an assay_lab the helper does nothing even if the RNG would otherwise fire."""
    w = bootstrap_genesis(seed=504, grid_width=10, grid_height=8, settler_count=2)
    settler = next(iter(p for p in w.parties if str(p).startswith("settler_")))
    plot_id = next(pid for pid, pl in w.plots.items() if pl.owner is None and pl.terrain != Terrain.WATER_DEEP and pl.terrain != Terrain.WATER_SHALLOW)
    plot = w.plots[plot_id]
    plot.terrain = Terrain.SWAMP
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.75,
    )
    assert claim_plot(w, settler, plot_id)["ok"] is True
    assert survey_plot(w, settler, plot_id)["ok"] is True
    w.tick = TICKS_PER_GAME_DAY
    with patch.object(w, "rng") as rng_mock:
        rng_mock.return_value = random.Random()
        rng_mock.return_value.random = lambda: 0.0
        _settler_probabilistic_discovery(w, settler)
    assert get_assay_stage(w, settler, MaterialId("sulfur_ore")) == 0


def test_settler_assay_lab_build_decision() -> None:
    """A settler with sulfur_grade ≥ 0.3 and the cash buffer chooses an assay_lab as Tier-2 build."""
    from realm.agents_genesis_settlers import _maybe_build_tier2_workshop
    from realm.core.ledger import system_reserve_account
    from realm.core.time_scale import legacy_scaled

    w = bootstrap_genesis(seed=510, grid_width=10, grid_height=8, settler_count=2)
    settler = next(iter(p for p in w.parties if str(p).startswith("settler_")))
    plot_id = next(
        pid
        for pid, pl in w.plots.items()
        if pl.owner is None
        and pl.terrain not in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP)
    )
    plot = w.plots[plot_id]
    plot.terrain = Terrain.SWAMP
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.55,
    )
    assert claim_plot(w, settler, plot_id)["ok"] is True
    assert survey_plot(w, settler, plot_id)["ok"] is True
    cash = party_cash_account(settler)
    tr = w.ledger.transfer(
        debit=system_reserve_account(),
        credit=cash,
        amount_cents=400_000,
    )
    assert tr is None or not hasattr(tr, "reason"), tr
    for mid, qty in (
        ("brick", 8),
        ("timber", 6),
        ("coal", 4),
        ("glass", 4),
    ):
        ad = w.inventory.add(settler, MaterialId(mid), qty)
        assert not isinstance(ad, MatterErr)
    w.tick = legacy_scaled(120)
    built = _maybe_build_tier2_workshop(w, settler, plot_id, plot)
    assert built is True
    assert any(
        b.get("party") == str(settler) and b.get("building_id") == "assay_lab"
        for b in w.plot_buildings
    )

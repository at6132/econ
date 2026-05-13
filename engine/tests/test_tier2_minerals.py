"""Tier-2 subsurface, per-party recipe books, Tier-2 extraction gates."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.production import start_production
from realm.recipes import RECIPES
from realm.terrain import Terrain
from realm.world import (
    SubsurfaceRoll,
    bootstrap_frontier,
    bootstrap_genesis,
    ensure_party_recipe_book,
    tier1_recipe_ids,
)


def test_tier2_subsurface_generated() -> None:
    """Bootstrap rolls Tier-2 grades on a meaningful share of plots."""
    w = bootstrap_genesis(seed=101, grid_width=24, grid_height=18, settler_count=2)
    plots = list(w.plots.values())
    n = len(plots)
    with_sulfur = sum(1 for p in plots if p.subsurface.sulfur_grade > 0.0)
    with_phosphate = sum(1 for p in plots if p.subsurface.phosphate_grade > 0.0)
    with_silica = sum(1 for p in plots if p.subsurface.silica_grade > 0.0)
    assert with_sulfur >= int(0.30 * n), with_sulfur
    assert with_phosphate >= int(0.30 * n), with_phosphate
    assert with_silica >= int(0.30 * n), with_silica
    assert w.ledger.total_cents() > 0


def test_party_recipe_book_starts_with_tier1() -> None:
    """Fresh party books contain every Tier-1 (non-discovery) recipe and zero Tier-2 recipes."""
    w = bootstrap_genesis(seed=102, grid_width=8, grid_height=6, settler_count=3)
    expected = tier1_recipe_ids()
    assert "sawmill" in expected and "smelt_iron" in expected and "hand_chop" in expected
    tier2_ids = {rid for rid, r in RECIPES.items() if r.requires_discovery}
    assert "mine_sulfur_ore" in tier2_ids and "hand_mine_tin" in tier2_ids
    for party in w.parties:
        book = w.party_recipe_books.get(str(party), set())
        assert expected.issubset(book), f"missing Tier-1 ids for {party}: {expected - book}"
        assert not (book & tier2_ids), f"Tier-2 leakage in {party}: {book & tier2_ids}"


def test_tier2_recipe_blocked_without_discovery() -> None:
    """A Tier-2 mining recipe is rejected as undiscovered even when everything else is ready."""
    w = bootstrap_frontier(seed=103, grid_width=6, grid_height=4)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    plot = w.plots[pid]
    plot.terrain = Terrain.SWAMP
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.6,
    )
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    ad = w.inventory.add(player, MaterialId("mining_pick"), 1)
    assert not isinstance(ad, MatterErr)
    r = start_production(w, player, pid, "hand_mine_sulfur")
    assert r["ok"] is False, r
    assert r.get("reason") == "recipe not yet discovered"


def test_tier2_recipe_runs_after_discovery() -> None:
    """Once the recipe is in the party's book, the same call succeeds and conservation holds."""
    w = bootstrap_frontier(seed=104, grid_width=6, grid_height=4)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    plot = w.plots[pid]
    plot.terrain = Terrain.SWAMP
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.6,
    )
    total0 = w.ledger.total_cents()
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    ad = w.inventory.add(player, MaterialId("mining_pick"), 1)
    assert not isinstance(ad, MatterErr)
    book = ensure_party_recipe_book(w, player)
    book.add("hand_mine_sulfur")
    r = start_production(w, player, pid, "hand_mine_sulfur")
    assert r["ok"] is True and r.get("started") is True, r
    assert w.ledger.total_cents() == total0


def test_world_public_dict_exposes_recipe_books_and_tier2_grades() -> None:
    """API view exposes the player's recipe book and Tier-2 grades on surveyed plots."""
    from realm.world import world_public_dict

    w = bootstrap_frontier(seed=105, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    out = world_public_dict(w)
    assert "party_recipe_books" in out
    assert "sawmill" in out["party_recipe_books"]["player"]
    surveyed_plot = next(pl for pl in out["plots"] if pl["id"] == pid)
    assert "sulfur_grade" in surveyed_plot["subsurface"]
    # Tier-3 must remain hidden until deep_survey
    assert "platinum_grade" not in surveyed_plot["subsurface"]

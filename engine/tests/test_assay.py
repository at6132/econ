"""Assay system — paid analysis, deterministic stage progression, recipe unlock."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.assay import (
    ASSAY_COST_CENTS,
    ASSAY_DURATION_TICKS,
    ASSAY_MAX_STAGE,
    assay_mineral,
    get_assay_stage,
    party_recipe_book_summary,
)
from realm.production.buildings import BUILDINGS, build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
from realm.world import SubsurfaceRoll, bootstrap_frontier
from turnkey_fixtures import grant_turnkey_self_materials


def _set_sulfur_plot(w, party: PartyId, pid: PlotId) -> None:
    plot = w.plots[pid]
    plot.terrain = Terrain.SWAMP
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.7,
    )
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid)["ok"] is True


def _force_complete_lab(w, party: PartyId, pid: PlotId) -> None:
    """Build an assay_lab via turnkey, then mark it operational immediately (skip construction timer)."""
    grant_turnkey_self_materials(w, party, "assay_lab")
    r = build_on_plot(w, party, pid, "assay_lab", build_mode="turnkey")
    assert r["ok"] is True
    inst = r["instance_id"]
    for b in w.plot_buildings:
        if b.get("instance_id") == inst:
            b["completes_at_tick"] = -1  # already finished
            return
    raise AssertionError("could not find newly built assay_lab")


def test_assay_requires_lab() -> None:
    """Without an assay_lab on the plot, the action is rejected."""
    w = bootstrap_frontier(seed=201, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _set_sulfur_plot(w, player, pid)
    r = assay_mineral(w, player, pid, MaterialId("sulfur_ore"))
    assert r["ok"] is False
    assert "lab" in r.get("reason", "").lower()


def test_assay_stage_progression() -> None:
    """Three successful assays drive stage 1 → 2 → 3 on the same mineral."""
    w = bootstrap_frontier(seed=202, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _set_sulfur_plot(w, player, pid)
    _force_complete_lab(w, player, pid)
    total0 = w.ledger.total_cents()
    for expected_stage in (1, 2, 3):
        r = assay_mineral(w, player, pid, MaterialId("sulfur_ore"))
        assert r["ok"] is True, r
        for _ in range(ASSAY_DURATION_TICKS + 1):
            advance_tick(w)
        assert get_assay_stage(w, player, MaterialId("sulfur_ore")) == expected_stage
    assert w.ledger.total_cents() == total0


def test_assay_unlocks_recipe() -> None:
    """Reaching stage 3 places the sulfur recipe chain into the player's recipe book."""
    w = bootstrap_frontier(seed=203, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _set_sulfur_plot(w, player, pid)
    _force_complete_lab(w, player, pid)
    for _ in range(3):
        r = assay_mineral(w, player, pid, MaterialId("sulfur_ore"))
        assert r["ok"] is True
        for _ in range(ASSAY_DURATION_TICKS + 1):
            advance_tick(w)
    book = w.party_recipe_books.get(str(player), set())
    assert "mine_sulfur_ore" in book
    assert "hand_mine_sulfur" in book
    summary = party_recipe_book_summary(w, player)
    rows = {row["mineral"]: row for row in summary["progress"]}
    assert rows["sulfur_ore"]["stage"] == ASSAY_MAX_STAGE


def test_assay_world_feed_entry() -> None:
    """Stage 3 emits a ``world_feed`` headline tagged ``recipe_discovery``."""
    w = bootstrap_frontier(seed=204, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _set_sulfur_plot(w, player, pid)
    _force_complete_lab(w, player, pid)
    for _ in range(3):
        r = assay_mineral(w, player, pid, MaterialId("sulfur_ore"))
        assert r["ok"] is True
        for _ in range(ASSAY_DURATION_TICKS + 1):
            advance_tick(w)
    feed_hits = [
        e
        for e in w.event_log
        if e.get("kind") == "world_feed" and e.get("feed_source") == "recipe_discovery"
    ]
    assert feed_hits, "expected at least one recipe_discovery world_feed row"
    assert any(str(e.get("mineral")) == "sulfur_ore" for e in feed_hits)


def test_assay_conservation_500c_per_attempt() -> None:
    """Every assay attempt charges exactly ``ASSAY_COST_CENTS`` to the system reserve; total invariant."""
    w = bootstrap_frontier(seed=205, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _set_sulfur_plot(w, player, pid)
    _force_complete_lab(w, player, pid)
    total0 = w.ledger.total_cents()
    cash0 = w.ledger.balance(party_cash_account(player))
    r = assay_mineral(w, player, pid, MaterialId("sulfur_ore"))
    assert r["ok"] is True
    assert r["cost_cents"] == ASSAY_COST_CENTS
    assert w.ledger.balance(party_cash_account(player)) == cash0 - ASSAY_COST_CENTS
    assert w.ledger.total_cents() == total0


def test_assay_blocks_double_submission() -> None:
    """Cannot start a second assay on the same mineral while one is in progress."""
    w = bootstrap_frontier(seed=206, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _set_sulfur_plot(w, player, pid)
    _force_complete_lab(w, player, pid)
    assert assay_mineral(w, player, pid, MaterialId("sulfur_ore"))["ok"] is True
    r2 = assay_mineral(w, player, pid, MaterialId("sulfur_ore"))
    assert r2["ok"] is False
    assert "in progress" in r2.get("reason", "")


def test_assay_low_subsurface_rejected() -> None:
    """Sub-threshold grade rejects an assay even if the lab is present."""
    w = bootstrap_frontier(seed=207, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    plot = w.plots[pid]
    plot.terrain = Terrain.PLAINS
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.05,
    )
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    _force_complete_lab(w, player, pid)
    r = assay_mineral(w, player, pid, MaterialId("sulfur_ore"))
    assert r["ok"] is False
    assert "subsurface" in r.get("reason", "").lower()

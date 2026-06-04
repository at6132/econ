"""Research lab — tech tree progress, daily ticks, patents."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import PartyId, PlotId
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.population.laborers import LaborerNPC
from realm.production.buildings import build_on_plot
from realm.research.research_lab import (
    RESEARCHER_SKILL_THRESHOLD,
    complete_research,
    count_party_researchers,
    party_research_summary,
    research_daily_bonus,
    start_research,
)
from realm.research.patents import tick_era_advancement
from realm.research.tech_tree import TECH_NODES
from realm.world.tick import advance_tick
from realm.world import bootstrap_frontier
from turnkey_fixtures import grant_turnkey_self_materials


def _unclaimed_plot(w) -> PlotId:
    for pid, plot in w.plots.items():
        if plot.owner is None and not str(plot.terrain.value).startswith("water"):
            return PlotId(str(pid))
    raise AssertionError("no unclaimed plot")


def _claim_surveyed(w, party: PartyId, pid: PlotId | None = None) -> PlotId:
    if pid is None:
        pid = _unclaimed_plot(w)
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid)["ok"] is True
    return pid


def _force_complete_research_lab(w, party: PartyId, pid: PlotId) -> None:
    grant_turnkey_self_materials(w, party, "research_lab")
    r = build_on_plot(w, party, pid, "research_lab", build_mode="turnkey")
    assert r["ok"] is True
    inst = r["instance_id"]
    for b in w.plot_buildings:
        if b.get("instance_id") == inst:
            b["completes_at_tick"] = -1
            return
    raise AssertionError("research_lab not found after build")


def _advance_game_days(w, days: int) -> None:
    for _ in range(days * TICKS_PER_GAME_DAY):
        advance_tick(w)


def _finish_industrial_era(w, party: PartyId) -> None:
    """Electrical-era nodes require all industrial tech nodes complete globally."""
    for nid in ("precision_tooling", "workshop_engineering"):
        assert complete_research(w, party, nid)["ok"] is True
    w.tick = max(int(w.tick), TICKS_PER_GAME_DAY)
    tick_era_advancement(w)


def test_start_requires_research_lab() -> None:
    w = bootstrap_frontier(seed=301, grid_width=4, grid_height=3)
    player = PartyId("player")
    r = start_research(w, player, "electric_motors")
    assert r["ok"] is False
    assert "research_lab" in r.get("reason", "")


def test_research_completes_and_unlocks_recipes() -> None:
    w = bootstrap_frontier(seed=302, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = _claim_surveyed(w, player)
    _force_complete_research_lab(w, player, pid)
    _finish_industrial_era(w, player)
    r = start_research(w, player, "electric_motors")
    assert r["ok"] is True
    cost = int(r["research_cost_days"])
    _advance_game_days(w, cost)
    summary = party_research_summary(w, player)
    assert "electric_motors" in summary["completed"]
    book = w.party_recipe_books.get(str(player), set())
    assert "electric_pump" in book
    assert "electric_drill" in book


def test_prerequisite_nodes_enforced() -> None:
    w = bootstrap_frontier(seed=303, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = _claim_surveyed(w, player)
    _force_complete_research_lab(w, player, pid)
    _finish_industrial_era(w, player)
    r = start_research(w, player, "telegraph")
    assert r["ok"] is False
    assert "prerequisite" in r.get("reason", "").lower()


def test_patent_awarded_to_first_global_completer() -> None:
    w = bootstrap_frontier(seed=304, grid_width=4, grid_height=3)
    a = PartyId("player")
    b = PartyId("npc_grain_vendor")
    assert complete_research(w, a, "electric_motors")["ok"] is True
    assert complete_research(w, b, "electric_motors")["ok"] is True
    first = w.scenario_state.get("research_global_first", {})
    assert first.get("electric_motors") == str(a)
    assert "electric_motors" in party_research_summary(w, a)["patents"]
    assert party_research_summary(w, b)["patents"] == []


def test_researchers_reduce_effective_cost() -> None:
    w = bootstrap_frontier(seed=305, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = _claim_surveyed(w, player)
    _force_complete_research_lab(w, player, pid)
    _finish_industrial_era(w, player)
    w.laborers["lab-1"] = LaborerNPC(
        laborer_id="lab-1",
        display_name="Researcher",
        island_id=0,
        home_plot_id=pid,
        employer=player,
        skill_level=float(RESEARCHER_SKILL_THRESHOLD),
    )
    w.laborers["lab-2"] = LaborerNPC(
        laborer_id="lab-2",
        display_name="Researcher 2",
        island_id=0,
        home_plot_id=pid,
        employer=player,
        skill_level=80.0,
    )
    assert count_party_researchers(w, player) == 2
    base = int(TECH_NODES["electric_motors"]["research_cost_days"])
    r = start_research(w, player, "electric_motors")
    assert r["ok"] is True
    assert int(r["research_cost_days"]) == (base + 1) // 2


def test_daily_bonus_capped() -> None:
    assert research_daily_bonus(1) == 0.0
    assert research_daily_bonus(2) == 0.5
    assert research_daily_bonus(9) == 3.0


def test_assay_and_research_do_not_share_state() -> None:
    """Assay jobs and research progress use separate scenario_state keys."""
    w = bootstrap_frontier(seed=306, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = _claim_surveyed(w, player)
    _force_complete_research_lab(w, player, pid)
    _finish_industrial_era(w, player)
    r = start_research(w, player, "electric_motors")
    assert r["ok"] is True
    assert "assay" not in (w.scenario_state.get("active_research") or {})
    assert w.scenario_state.get("assay") is None or isinstance(
        w.scenario_state.get("assay"), dict
    )
    assert str(player) in w.scenario_state.get("active_research", {})

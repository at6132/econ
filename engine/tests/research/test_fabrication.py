"""Fabrication capabilities, custom build gates, workshop focus."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import PartyId, PlotId
from realm.production.custom_content import create_custom_recipe, register_custom_material
from realm.research.capabilities import party_has_capability
from realm.research.research_lab import complete_research
from realm.research.workshop_focus import set_workshop_focus, workshop_focus_multiplier
from realm.actions.blueprint_actions import create_blueprint
from realm.world import bootstrap_frontier


def _claim(w, party: PartyId) -> PlotId:
    for pid, plot in w.plots.items():
        if plot.owner is None and not str(plot.terrain.value).startswith("water"):
            pid = PlotId(str(pid))
            assert claim_plot(w, party, pid)["ok"] is True
            assert survey_plot(w, party, pid)["ok"] is True
            return pid
    raise AssertionError("no plot")


def test_boot_custom_material_only() -> None:
    w = bootstrap_frontier(seed=501, grid_width=3, grid_height=3)
    player = PartyId("player")
    assert party_has_capability(w, player, "custom_material")
    assert not party_has_capability(w, player, "custom_recipe")
    r = create_custom_recipe(
        w,
        player,
        "Test line",
        {"timber": 1},
        {"lumber": 1},
        60,
        100,
        "",
    )
    assert r["ok"] is False


def test_precision_tooling_unlocks_custom_recipe() -> None:
    w = bootstrap_frontier(seed=502, grid_width=3, grid_height=3)
    player = PartyId("player")
    complete_research(w, player, "precision_tooling")
    assert party_has_capability(w, player, "custom_recipe")
    reg = register_custom_material(w, player, "Player alloy", material_id="player_alloy")
    assert reg["ok"] is True
    r = create_custom_recipe(
        w,
        player,
        "Alloy line",
        {"player_alloy": 1},
        {"player_alloy": 2},
        120,
        500,
        "",
    )
    assert r["ok"] is True


def test_blueprint_requires_workshop_engineering() -> None:
    w = bootstrap_frontier(seed=503, grid_width=3, grid_height=3)
    player = PartyId("player")
    r = create_blueprint(
        w,
        player,
        "Shed",
        "",
        2,
        2,
        {},
        10_000,
        1440,
        ["sawmill"],
        0,
        {},
        0,
        False,
        0,
        "custom",
        [],
        False,
        False,
    )
    assert r["ok"] is False
    complete_research(w, player, "precision_tooling")
    complete_research(w, player, "workshop_engineering")
    r2 = create_blueprint(
        w,
        player,
        "Shed",
        "",
        2,
        2,
        {},
        10_000,
        1440,
        ["sawmill"],
        0,
        {},
        0,
        False,
        0,
        "custom",
        [],
        False,
        False,
    )
    assert r2["ok"] is True


def test_workshop_focus_after_electric_motors() -> None:
    w = bootstrap_frontier(seed=504, grid_width=3, grid_height=3)
    player = PartyId("player")
    pid = _claim(w, player)
    complete_research(w, player, "electric_motors")
    assert party_has_capability(w, player, "workshop_focus")
    r = set_workshop_focus(w, player, pid, "grow_grain")
    assert r["ok"] is True
    assert workshop_focus_multiplier(w, player, pid, "grow_grain") == 1.15
    assert workshop_focus_multiplier(w, player, pid, "mine_coal") < 1.0

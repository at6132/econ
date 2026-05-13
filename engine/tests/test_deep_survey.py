"""Deep survey — drill_rig, Tier-3 mineral reveal, drill_bit consumption, conservation."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.buildings import BUILDINGS, build_on_plot
from realm.deep_survey import (
    DEEP_SURVEY_COST_CENTS,
    DEEP_SURVEY_DURATION_TICKS,
    deep_survey,
)
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import party_cash_account
from realm.terrain import Terrain
from realm.tick import advance_tick
from realm.world import SubsurfaceRoll, bootstrap_frontier, world_public_dict
from turnkey_fixtures import grant_turnkey_self_materials


def _finish_building(w, party: PartyId, pid: PlotId, building_id: str) -> None:
    grant_turnkey_self_materials(w, party, building_id)
    r = build_on_plot(w, party, pid, building_id, build_mode="turnkey")
    assert r["ok"] is True, r
    inst = r["instance_id"]
    for b in w.plot_buildings:
        if b.get("instance_id") == inst:
            b["completes_at_tick"] = -1
            return
    raise AssertionError(f"missing building row for {building_id}")


def _setup_plot_with_platinum(w, party: PartyId, pid: PlotId) -> None:
    plot = w.plots[pid]
    plot.terrain = Terrain.MOUNTAIN
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        platinum_grade=0.65,
        oil_shale_grade=0.0,
        rare_earth_grade=0.0,
    )
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid)["ok"] is True


def test_deep_survey_requires_drill_rig() -> None:
    """Without an installed drill_rig the action is rejected."""
    w = bootstrap_frontier(seed=401, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_plot_with_platinum(w, player, pid)
    ad = w.inventory.add(player, MaterialId("drill_bit"), 1)
    assert not isinstance(ad, MatterErr)
    r = deep_survey(w, player, pid)
    assert r["ok"] is False
    assert "drill_rig" in r.get("reason", "")


def test_deep_survey_consumes_drill_bit() -> None:
    """A successful submission immediately removes 1 drill_bit and 2_000c."""
    w = bootstrap_frontier(seed=402, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_plot_with_platinum(w, player, pid)
    _finish_building(w, player, pid, "drill_rig")
    ad = w.inventory.add(player, MaterialId("drill_bit"), 2)
    assert not isinstance(ad, MatterErr)
    bits0 = w.inventory.qty(player, MaterialId("drill_bit"))
    cash0 = w.ledger.balance(party_cash_account(player))
    total0 = w.ledger.total_cents()
    r = deep_survey(w, player, pid)
    assert r["ok"] is True, r
    assert w.inventory.qty(player, MaterialId("drill_bit")) == bits0 - 1
    assert w.ledger.balance(party_cash_account(player)) == cash0 - DEEP_SURVEY_COST_CENTS
    assert w.ledger.total_cents() == total0


def test_deep_survey_reveals_tier3_grades() -> None:
    """After completion the plot exposes Tier-3 grades through ``world_public_dict``."""
    w = bootstrap_frontier(seed=403, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_plot_with_platinum(w, player, pid)
    _finish_building(w, player, pid, "drill_rig")
    ad = w.inventory.add(player, MaterialId("drill_bit"), 1)
    assert not isinstance(ad, MatterErr)
    before = world_public_dict(w)
    sub_before = next(pl for pl in before["plots"] if pl["id"] == pid)["subsurface"]
    assert "platinum_grade" not in sub_before
    r = deep_survey(w, player, pid)
    assert r["ok"] is True
    for _ in range(DEEP_SURVEY_DURATION_TICKS + 2):
        advance_tick(w)
    assert w.plots[pid].deep_surveyed is True
    after = world_public_dict(w)
    sub_after = next(pl for pl in after["plots"] if pl["id"] == pid)["subsurface"]
    assert "platinum_grade" in sub_after
    assert sub_after["platinum_grade"] > 0.0


def test_deep_survey_conservation_no_inventory_leak_on_money_error() -> None:
    """A successful run preserves total_cents (cost goes to system reserve)."""
    w = bootstrap_frontier(seed=404, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_plot_with_platinum(w, player, pid)
    _finish_building(w, player, pid, "drill_rig")
    ad = w.inventory.add(player, MaterialId("drill_bit"), 1)
    assert not isinstance(ad, MatterErr)
    total0 = w.ledger.total_cents()
    r = deep_survey(w, player, pid)
    assert r["ok"] is True
    for _ in range(DEEP_SURVEY_DURATION_TICKS + 2):
        advance_tick(w)
    assert w.ledger.total_cents() == total0


def test_deep_survey_emits_world_feed_when_notable() -> None:
    """A platinum_grade ≥ 0.1 finding emits a ``deep_survey_find`` world_feed row."""
    w = bootstrap_frontier(seed=405, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_plot_with_platinum(w, player, pid)
    _finish_building(w, player, pid, "drill_rig")
    ad = w.inventory.add(player, MaterialId("drill_bit"), 1)
    assert not isinstance(ad, MatterErr)
    assert deep_survey(w, player, pid)["ok"] is True
    for _ in range(DEEP_SURVEY_DURATION_TICKS + 2):
        advance_tick(w)
    hits = [
        e
        for e in w.event_log
        if e.get("kind") == "world_feed" and e.get("feed_source") == "deep_survey_find"
    ]
    assert hits
    assert any(str(e.get("plot_id")) == str(pid) for e in hits)

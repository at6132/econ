"""Sprint 6 — Phase D.4: ``/world/summary`` lightweight HUD payload."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import PartyId, PlotId
from realm.world import bootstrap_genesis, world_summary_dict


REQUIRED_KEYS = {
    "tick",
    "party",
    "cash",
    "inventory_value_estimate",
    "net_worth_estimate",
    "active_production",
    "maintenance_warnings",
    "unread_npc_messages",
    "unread_feed_entries",
    "active_contracts",
    "open_orders",
}


def test_world_summary_shape_for_player() -> None:
    w = bootstrap_genesis(seed=23, grid_width=12, grid_height=10, settler_count=2)
    s = world_summary_dict(w, PartyId("player"))
    missing = REQUIRED_KEYS - set(s.keys())
    assert not missing, f"missing keys: {missing}"
    assert s["party"] == "player"
    assert isinstance(s["cash"], int)
    assert isinstance(s["active_production"], list)


def test_world_summary_reflects_player_state() -> None:
    w = bootstrap_genesis(seed=29, grid_width=14, grid_height=12, settler_count=2)
    p = PartyId("player")
    pid = PlotId("p-0-0")
    s0 = world_summary_dict(w, p)
    assert claim_plot(w, p, pid)["ok"] is True
    s1 = world_summary_dict(w, p)
    # Cash dropped by the claim cost.
    assert s1["cash"] < s0["cash"]
    # Net-worth estimate is non-negative.
    assert s1["net_worth_estimate"] >= 0


def test_world_summary_excludes_plots_grid() -> None:
    w = bootstrap_genesis(seed=31, grid_width=12, grid_height=10, settler_count=2)
    s = world_summary_dict(w, PartyId("player"))
    # Summary must NOT include the full plots grid (that's what /world is for).
    assert "plots" not in s
    assert "plot_buildings" not in s

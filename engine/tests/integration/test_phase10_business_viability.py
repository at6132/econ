"""Phase 10G — headless slice: business survives 15 game-days."""

from __future__ import annotations

from realm.actions.business_actions import register_business
from realm.actions.plot_actions import claim_plot
from realm.core.ids import PartyId, PlotId
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def test_phase10_business_stays_active_after_multi_day_run() -> None:
    w = bootstrap_genesis(seed=101, grid_width=22, grid_height=18, settler_count=5)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    r = register_business(
        w,
        player,
        "Frontier Retail",
        "",
        template_id="general_store",
        registered_plot_ids=(str(pid),),
    )
    assert r["ok"] is True
    bid = str(r["business_id"])
    for _ in range(3 * 1440):
        advance_tick(w)
    assert w.businesses[bid].status == "active"

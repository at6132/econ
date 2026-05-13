"""Headless integration: prereq materials, settler tool buys, Tier-0 loop, conservation."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.tick import advance_tick
from realm.world import bootstrap_genesis


def test_prereq_integration_genesis_supply_chain_headless() -> None:
    w = bootstrap_genesis(seed=600, grid_width=22, grid_height=18, settler_count=24)
    total0 = w.ledger.total_cents()
    ex = PartyId("genesis_exchange")
    for _ in range(720):
        advance_tick(w)
    picks = sum(
        1
        for p in w.parties
        if str(p).startswith("settler_") and w.inventory.qty(p, MaterialId("mining_pick")) >= 1
    )
    assert picks >= 14
    for _ in range(900):
        advance_tick(w)
    settler_buildings = sum(
        1 for b in w.plot_buildings if str(b.get("party", "")).startswith("settler_")
    )
    assert settler_buildings >= 16
    parties_on_book: set[str] = set()
    for lst in w.market_asks_by_material.values():
        for o in lst:
            if o.party != ex and str(o.party).startswith("settler_"):
                parties_on_book.add(str(o.party))
    assert len(parties_on_book) >= 2
    gst = w.scenario_state.get("genesis", {})
    assert int(gst.get("hand_tier0_completions", 0)) >= 1
    assert w.ledger.total_cents() == total0

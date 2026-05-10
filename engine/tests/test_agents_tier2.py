"""Tier 2 optimizing agents — smoke + conservation."""

from __future__ import annotations

from realm.ids import PartyId
from realm.tick import advance_tick
from realm.world import bootstrap_frontier


def test_tier2_parties_exist_in_bootstrap() -> None:
    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    for name in (
        "t2_ele_bidstack",
        "t2_lumber_bid",
        "t2_timber_spread",
        "t2_clay_sweep",
        "t2_coal_spread",
    ):
        assert PartyId(name) in w.parties


def test_advance_tick_with_tier2_conserves_ledger_total() -> None:
    w = bootstrap_frontier(seed=90, grid_width=3, grid_height=3)
    t0 = w.ledger.total_cents()
    for _ in range(80):
        advance_tick(w)
    assert w.ledger.total_cents() == t0

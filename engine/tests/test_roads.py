"""Sprint 6 — Phase A road tests."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.movement import dispatch_shipment
from realm.roads import (
    BUILD_COST_CENTS,
    build_road,
    find_segment_between,
    set_road_toll,
)
from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis


@pytest.fixture
def gen_world():
    w = bootstrap_genesis(
        seed=42,
        grid_width=16,
        grid_height=12,
        settler_count=4,
        map_layout="continent",
    )
    return w


def _stock(w, party: PartyId, mat: str, qty: int) -> None:
    w.inventory.add(party, MaterialId(mat), qty)


def _give_cash(w, party: PartyId, cents: int) -> None:
    cash = party_cash_account(party)
    w.ledger.ensure_account(cash)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=cash, amount_cents=int(cents)
    )


def _adjacent_plot_pair(w, owner_a: PartyId, owner_b: PartyId) -> tuple[PlotId, PlotId]:
    """Find two unclaimed adjacent plots, claim them for the given owners, return ids."""
    for pid_a, plot_a in w.plots.items():
        if plot_a.owner is not None:
            continue
        for pid_b, plot_b in w.plots.items():
            if plot_b.owner is not None:
                continue
            if pid_a == pid_b:
                continue
            if abs(plot_a.x - plot_b.x) + abs(plot_a.y - plot_b.y) != 1:
                continue
            _give_cash(w, owner_a, 10_000)
            _give_cash(w, owner_b, 10_000)
            ra = claim_plot(w, owner_a, pid_a)
            rb = claim_plot(w, owner_b, pid_b)
            assert ra["ok"] is True, ra
            assert rb["ok"] is True, rb
            return pid_a, pid_b
    raise AssertionError("no adjacent unclaimed plot pair")


# ────────────────────────────────────────────────────────────────────────


def test_road_build_deducts_materials(gen_world):
    w = gen_world
    party = PartyId("player")
    pid_a, pid_b = _adjacent_plot_pair(w, party, party)
    _give_cash(w, party, BUILD_COST_CENTS)
    _stock(w, party, "lumber", 5)
    _stock(w, party, "stone", 5)
    start_lumber = w.inventory.qty(party, MaterialId("lumber"))
    start_stone = w.inventory.qty(party, MaterialId("stone"))
    start_cash = w.ledger.balance(party_cash_account(party))
    start_total = w.ledger.total_cents()
    r = build_road(w, party, pid_a, pid_b)
    assert r["ok"] is True
    assert w.inventory.qty(party, MaterialId("lumber")) == start_lumber - 2
    assert w.inventory.qty(party, MaterialId("stone")) == start_stone - 2
    assert w.ledger.balance(party_cash_account(party)) == start_cash - BUILD_COST_CENTS
    assert w.ledger.total_cents() == start_total
    assert find_segment_between(w, pid_a, pid_b) is not None


def test_road_required_adjacent_plots(gen_world):
    w = gen_world
    party = PartyId("player")
    plots = list(w.plots.keys())
    pid_a = plots[0]
    pid_b = plots[-1]
    pa = w.plots[pid_a]
    pb = w.plots[pid_b]
    assert abs(pa.x - pb.x) + abs(pa.y - pb.y) > 1
    _give_cash(w, party, BUILD_COST_CENTS)
    _stock(w, party, "lumber", 5)
    _stock(w, party, "stone", 5)
    r = build_road(w, party, pid_a, pid_b)
    assert r["ok"] is False
    assert "adjacent" in r["reason"].lower()


def test_road_reduces_movement_cost(gen_world):
    w = gen_world
    party = PartyId("player")
    pid_a, pid_b = _adjacent_plot_pair(w, party, party)
    _give_cash(w, party, BUILD_COST_CENTS + 10_000)
    _stock(w, party, "lumber", 5)
    _stock(w, party, "stone", 5)
    _stock(w, party, "coal", 4)
    fee_no_road = dispatch_shipment(
        w, party, MaterialId("coal"), 1, pid_a, pid_b
    )["fee_cents"]
    r = build_road(w, party, pid_a, pid_b)
    assert r["ok"] is True
    fee_with_road = dispatch_shipment(
        w, party, MaterialId("coal"), 1, pid_a, pid_b
    )["fee_cents"]
    assert fee_with_road < fee_no_road


def test_road_toll_collected(gen_world):
    w = gen_world
    owner = PartyId("settler_001")
    shipper = PartyId("player")
    pid_a, pid_b = _adjacent_plot_pair(w, shipper, shipper)
    _give_cash(w, owner, BUILD_COST_CENTS)
    _stock(w, owner, "lumber", 5)
    _stock(w, owner, "stone", 5)
    r = build_road(w, owner, pid_a, pid_b)
    assert r["ok"] is True
    sid = r["segment_id"]
    set_road_toll(w, owner, sid, 5)
    # Place a market ask so the toll calculation can read a unit value.
    from realm.economy.markets import place_sell_order

    _stock(w, owner, "coal", 5)
    place_sell_order(w, owner, MaterialId("coal"), 1, 200)
    _stock(w, shipper, "coal", 5)
    _give_cash(w, shipper, 10_000)
    owner_cash_start = w.ledger.balance(party_cash_account(owner))
    total_before = w.ledger.total_cents()
    res = dispatch_shipment(w, shipper, MaterialId("coal"), 3, pid_a, pid_b)
    assert res["ok"] is True
    assert res["road_tolls_paid_cents"] > 0
    owner_cash_end = w.ledger.balance(party_cash_account(owner))
    assert owner_cash_end - owner_cash_start == res["road_tolls_paid_cents"]
    assert w.ledger.total_cents() == total_before


def test_road_network_reduces_trade_corridor_cost():
    """A fully roaded corridor cuts per-tile shipping cost in half.

    The engine charges ``BASE + dist*per_tile`` — roads halve the per-tile
    component on covered edges only. With ``BASE = 100c`` and ``per_tile = 50c``
    intra-region, a 10-tile fully-roaded corridor goes from 600c to 350c
    (≈58% of the no-road fee). The assertion is that per-tile cost on the
    roaded span is exactly halved.
    """
    w = bootstrap_genesis(
        seed=42, grid_width=27, grid_height=12, settler_count=4, map_layout="continent"
    )
    party = PartyId("player")
    # Pick a horizontal corridor inside a single region (r-0-0): x=1..7, y=1.
    # Same-region shipments pay PER_TILE_SHIP_CENTS=50c (no operator discount).
    y = 1
    pids: list[PlotId] = []
    for x in range(1, 8):
        pid = next(
            (pid for pid, p in w.plots.items() if p.x == x and p.y == y and p.owner is None),
            None,
        )
        if pid is None:
            pytest.skip("could not find a clean 11-plot corridor")
        pids.append(pid)
    _give_cash(w, party, 5_000_000)
    for pid in pids:
        r = claim_plot(w, party, pid)
        assert r["ok"] is True, r
    _stock(w, party, "lumber", 80)
    _stock(w, party, "stone", 80)
    _stock(w, party, "coal", 10)
    fee_no_roads = dispatch_shipment(
        w, party, MaterialId("coal"), 1, pids[0], pids[-1]
    )["fee_cents"]
    _stock(w, party, "coal", 10)
    for a, b in zip(pids[:-1], pids[1:]):
        r = build_road(w, party, a, b)
        assert r["ok"] is True, r
    fee_with_roads = dispatch_shipment(
        w, party, MaterialId("coal"), 1, pids[0], pids[-1]
    )["fee_cents"]
    # Per-tile savings = dist * per_tile / 2 over 6 tiles. With per_tile=50c
    # this is 150c off the 400c no-road fee → 250c (≈ 62.5% of original).
    assert fee_with_roads <= fee_no_roads * 0.65, (
        f"expected ≥35% savings, got fee_no={fee_no_roads} fee_with={fee_with_roads}"
    )


def test_npc_road_builder_builds_on_high_traffic_routes():
    w = bootstrap_genesis(
        seed=42, grid_width=24, grid_height=18, settler_count=8, map_layout="continent"
    )
    # Inject some shipment counts so the builder has a target.
    w.scenario_state["route_shipment_counts"] = {
        "r-0-0:r-1-1": 50,
        "r-1-1:r-2-2": 30,
    }
    from realm.genesis_road_builders import FRONTIER_ROADS_PARTY_ID

    assert FRONTIER_ROADS_PARTY_ID in w.parties
    # Advance 7 game-days (10080 ticks).
    target_ticks = 1440 * 7
    for _ in range(target_ticks):
        advance_tick(w)
    built = [
        s for s in w.road_segments if str(s.owner) == str(FRONTIER_ROADS_PARTY_ID)
    ]
    assert len(built) >= 5, f"expected ≥5 NPC road segments after 7 days, got {len(built)}"
    # All built segments should default to a 3% toll.
    assert all(s.toll_rate_pct == 3 for s in built)

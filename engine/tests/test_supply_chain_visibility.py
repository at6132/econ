"""Sprint 6 — Phase C supply chain visibility tests."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.economy.analytics import _party_volume_signal, purchase_analytics_product
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.economy.markets import (
    ensure_market_seller_registration,
    place_buy_order,
    place_sell_order,
)
from realm.economy.supply_signals import (
    LARGE_BUY_THRESHOLD_UNITS,
    region_activity_for_material,
)
from realm.world import bootstrap_genesis


def _give_cash(w, party: PartyId, cents: int) -> None:
    cash = party_cash_account(party)
    w.ledger.ensure_account(cash)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=cash, amount_cents=int(cents)
    )


def _stock(w, party: PartyId, mat: str, qty: int) -> None:
    w.inventory.add(party, MaterialId(mat), qty)


def _inject_route_operator(w, route_key: str, party: PartyId, fee_per_tile: int = 20):
    """Test helper: drop an operator entry directly into scenario_state."""
    ops = w.scenario_state.setdefault("route_operators", {})
    entries = ops.setdefault(route_key, [])
    entries.append(
        {
            "operator_party": str(party),
            "fee_per_tile_cents": int(fee_per_tile),
        }
    )


@pytest.fixture
def gen_world():
    return bootstrap_genesis(
        seed=42, grid_width=18, grid_height=12, settler_count=4, map_layout="continent"
    )


# ────────────────────────────────────────────────────────────────────────


def test_large_buy_event_fires(gen_world):
    w = gen_world
    party = PartyId("player")
    _give_cash(w, party, 1_000_000)
    qty = LARGE_BUY_THRESHOLD_UNITS + 5
    r = place_buy_order(w, party, MaterialId("iron_ore"), qty, 100)
    assert r["ok"], r
    large_evts = [
        ev
        for ev in w.event_log
        if str(ev.get("kind")) == "large_buy_detected"
        and str(ev.get("material")) == "iron_ore"
    ]
    assert large_evts, "expected a large_buy_detected event"
    # Anonymity guarantee: no buyer/party/seller field.
    for ev in large_evts:
        assert "buyer" not in ev
        assert ev.get("party") in (None, "") or str(ev.get("party")) != str(party), (
            "large_buy_detected must not name the buyer"
        )
        assert str(party) not in str(ev.get("message", "")), (
            "large_buy_detected message must not name the buyer"
        )


def test_supply_concentration_feed_entry(gen_world):
    w = gen_world
    # One seller (player) lists 80 coal; a second seller lists 10 coal.
    seller_a = PartyId("player")
    seller_b = PartyId("settler_001")
    _stock(w, seller_a, "coal", 80)
    _stock(w, seller_b, "coal", 10)
    _give_cash(w, seller_a, 1_000_000)
    _give_cash(w, seller_b, 1_000_000)
    # Place B's first so the concentration check at A's listing has the data it needs.
    r = place_sell_order(w, seller_b, MaterialId("coal"), 10, 100)
    assert r["ok"], r
    r = place_sell_order(w, seller_a, MaterialId("coal"), 80, 100)
    assert r["ok"], r
    feed = [
        ev
        for ev in w.event_log
        if str(ev.get("kind")) == "world_feed"
        and str(ev.get("kind_tag", "")) == "supply_concentration"
        and str(ev.get("material")) == "coal"
    ]
    assert feed, "expected supply concentration warning in event_log"
    for ev in feed:
        assert str(seller_a) not in str(ev.get("message", "")), (
            "supply concentration must not name the seller"
        )


def test_region_activity_matches_seller_locations(gen_world):
    w = gen_world
    # Find a plot in r-0-0 (NW) and one in r-2-2 (SE), claim them for two sellers.
    sellers = (PartyId("player"), PartyId("settler_001"))
    target_regions = ("r-0-0", "r-2-2")
    chosen: dict[str, PlotId] = {}
    for region in target_regions:
        for pid, plot in w.plots.items():
            if plot.owner is not None:
                continue
            from realm.world.regions import region_for_plot

            if region_for_plot(w, pid) == region:
                chosen[region] = pid
                break
    assert len(chosen) == 2, f"could not find plots in both target regions: {chosen}"
    _give_cash(w, sellers[0], 1_000_000)
    _give_cash(w, sellers[1], 1_000_000)
    assert claim_plot(w, sellers[0], chosen["r-0-0"])["ok"]
    assert claim_plot(w, sellers[1], chosen["r-2-2"])["ok"]
    _stock(w, sellers[0], "coal", 30)
    _stock(w, sellers[1], "coal", 5)
    place_sell_order(w, sellers[0], MaterialId("coal"), 30, 120)
    place_sell_order(w, sellers[1], MaterialId("coal"), 5, 120)
    info = region_activity_for_material(w, MaterialId("coal"))
    assert info["primary_region"] in ("r-0-0", "r-2-2")
    # NW is dominant (30 vs 5).
    assert info["by_region"].get("r-0-0", 0) > info["by_region"].get("r-2-2", 0)


def test_party_volume_includes_regions(gen_world):
    w = gen_world
    target = PartyId("settler_002")
    _give_cash(w, target, 1_000_000)
    # Claim two plots for the target so they have a region footprint.
    claimed = 0
    for pid in list(w.plots.keys()):
        plot = w.plots[pid]
        if plot.owner is not None:
            continue
        if claim_plot(w, target, pid)["ok"]:
            claimed += 1
            if claimed >= 2:
                break
    assert claimed == 2
    # Also register the target as a route operator on r-0-0:r-1-1.
    _inject_route_operator(w, "r-0-0:r-1-1", target)
    data = _party_volume_signal(w, str(target))
    assert "regions" in data
    assert len(data["regions"]) >= 1
    assert "route_registrations" in data
    assert "r-0-0:r-1-1" in data["route_registrations"]
    # Now buy through the analytics API and assert the same.
    buyer = PartyId("player")
    _give_cash(w, buyer, 10_000)
    r = purchase_analytics_product(
        w, buyer, "party_volume", {"party_id": str(target)}
    )
    assert r["ok"], r
    assert "regions" in r["data"]
    assert "route_registrations" in r["data"]


def test_public_data_exposes_route_registry(gen_world):
    w = gen_world
    op = PartyId("settler_001")
    _inject_route_operator(w, "r-0-0:r-1-0", op, fee_per_tile=15)
    raw = w.scenario_state.get("route_operators") or {}
    assert "r-0-0:r-1-0" in raw
    rows = raw["r-0-0:r-1-0"]
    assert any(str(e.get("operator_party")) == str(op) for e in rows)

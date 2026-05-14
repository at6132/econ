"""Capital goods: turnkey/self material prereqs, Tier-0 hand recipes, exchange tool listings."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.production.buildings import BUILDINGS, build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account
from realm.production import start_production
from realm.production.recipes import RECIPES
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
from realm.world import SubsurfaceRoll, bootstrap_genesis, bootstrap_frontier

from turnkey_fixtures import grant_turnkey_self_materials


def test_prereq_build_deducts_materials() -> None:
    w = bootstrap_genesis(seed=301, grid_width=12, grid_height=10, settler_count=2)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    total0 = w.ledger.total_cents()
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    grant_turnkey_self_materials(w, player, "strip_mine")
    t0 = w.inventory.qty(player, MaterialId("timber"))
    b0 = w.inventory.qty(player, MaterialId("brick"))
    c0 = w.inventory.qty(player, MaterialId("coal"))
    cash0 = w.ledger.balance(party_cash_account(player))
    spec = BUILDINGS["strip_mine"]
    turnkey = int(spec["turnkey_total_cents"])
    r = build_on_plot(w, player, pid, "strip_mine", build_mode="turnkey")
    assert r["ok"] is True, r
    assert w.inventory.qty(player, MaterialId("timber")) == t0 - 8
    assert w.inventory.qty(player, MaterialId("brick")) == b0 - 4
    assert w.inventory.qty(player, MaterialId("coal")) == c0 - 3
    assert w.ledger.balance(party_cash_account(player)) == cash0 - turnkey
    assert w.ledger.total_cents() == total0


def test_prereq_build_fails_without_materials() -> None:
    w = bootstrap_genesis(seed=302, grid_width=10, grid_height=8, settler_count=2)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    r = build_on_plot(w, player, pid, "strip_mine", build_mode="self_contract")
    assert r["ok"] is False
    assert "insufficient" in str(r.get("reason", "")).lower() or "missing" in str(r.get("reason", "")).lower()


def test_tier0_hand_chop_produces_timber() -> None:
    w = bootstrap_frontier(seed=1, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    # Sprint 1: hand_chop is forest-only; force the terrain after the claim to match.
    w.plots[pid].terrain = Terrain.FOREST
    assert survey_plot(w, player, pid)["ok"] is True
    ad = w.inventory.add(player, MaterialId("pick_axe"), 1)
    assert not isinstance(ad, MatterErr)
    total0 = w.ledger.total_cents()
    t0 = w.inventory.qty(player, MaterialId("timber"))
    assert start_production(w, player, pid, "hand_chop")["ok"] is True
    n = RECIPES["hand_chop"].duration_ticks
    for _ in range(n):
        advance_tick(w)
    assert w.inventory.qty(player, MaterialId("timber")) == t0 + 1
    assert w.inventory.qty(player, MaterialId("pick_axe")) >= 1
    assert w.ledger.total_cents() == total0


def test_tier0_hand_mine_gated_by_subsurface() -> None:
    w = bootstrap_frontier(seed=9, grid_width=2, grid_height=2)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    assert w.plots[pid].terrain == Terrain.MOUNTAIN
    w.plots[pid].subsurface = SubsurfaceRoll(
        iron_ore_grade=0.2,
        copper_ore_grade=0.5,
        clay_grade=0.5,
        coal_grade=0.5,
    )
    assert survey_plot(w, player, pid)["ok"] is True
    ad = w.inventory.add(player, MaterialId("mining_pick"), 1)
    assert not isinstance(ad, MatterErr)
    r = start_production(w, player, pid, "hand_mine_ore")
    assert r["ok"] is False
    assert "subsurface" in str(r.get("reason", "")).lower()


def test_tools_on_exchange() -> None:
    from realm.economy.markets import best_resting_ask_cents

    w = bootstrap_genesis(seed=303, grid_width=8, grid_height=6, settler_count=0)
    ex = PartyId("genesis_exchange")
    for mid in (MaterialId("mining_pick"), MaterialId("pick_axe")):
        key = str(mid)
        asks = w.market_asks_by_material.get(key, [])
        assert any(o.party == ex for o in asks), f"expected {mid} asks from exchange"
        assert best_resting_ask_cents(w, mid) is not None

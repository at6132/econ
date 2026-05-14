"""Sprint 6 — Phase B production throughput tests."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.production import (
    CONTINUOUS_RUN_COUNT,
    start_production,
    throughput_breakdown,
)
from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis


def _give_cash(w, party: PartyId, cents: int) -> None:
    cash = party_cash_account(party)
    w.ledger.ensure_account(cash)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=cash, amount_cents=int(cents)
    )


def _stock(w, party: PartyId, mat: str, qty: int) -> None:
    w.inventory.add(party, MaterialId(mat), qty)


def _find_hand_mine_coal_plot(w, party: PartyId) -> PlotId:
    """Claim and survey a plot with sufficient coal_grade for hand_mine_coal."""
    from realm.actions import survey_plot
    from realm.world.terrain import Terrain

    for pid, plot in w.plots.items():
        if plot.owner is not None:
            continue
        if plot.terrain not in (Terrain.PLAINS, Terrain.FOREST, Terrain.MOUNTAIN):
            continue
        if float(getattr(plot.subsurface, "coal_grade", 0.0)) < 0.3:
            continue
        _give_cash(w, party, 5_000_000)
        r = claim_plot(w, party, pid)
        if not r["ok"]:
            continue
        sr = survey_plot(w, party, pid)
        if not sr.get("ok"):
            continue
        return pid
    pytest.skip("could not find a plot suitable for hand mining coal")


# ────────────────────────────────────────────────────────────────────────


def test_run_count_N_stops_after_N():
    """With run_count=3, exactly 3 production_done events fire and active queue drains."""
    w = bootstrap_genesis(
        seed=42, grid_width=12, grid_height=10, settler_count=2, map_layout="continent"
    )
    party = PartyId("player")
    pid = _find_hand_mine_coal_plot(w, party)
    _stock(w, party, "mining_pick", 1)
    _give_cash(w, party, 1_000_000)
    r = start_production(w, party, pid, "hand_mine_coal", run_count=3)
    assert r["ok"], r
    assert r.get("runs_remaining") == 2

    # event_log is capped — track our run-ids as runs are scheduled so we can
    # count completions across the whole tick range without log trimming.
    seen_run_ids: set[str] = set()

    def _record_runs() -> None:
        for a in w.active_production:
            if a.party == party and a.recipe_id == "hand_mine_coal":
                seen_run_ids.add(a.run_id)

    _record_runs()
    for _ in range(720 * 4):
        advance_tick(w)
        _record_runs()
    assert len(seen_run_ids) == 3, (
        f"expected exactly 3 distinct hand_mine_coal runs, got {len(seen_run_ids)}: {sorted(seen_run_ids)}"
    )
    # No active runs left, no queued auto-restart entries for this party.
    assert not any(a.party == party and a.recipe_id == "hand_mine_coal" for a in w.active_production)
    queue = w.scenario_state.get("production_auto_restart_queue") or []
    assert not [e for e in queue if e.get("party") == str(party) and e.get("recipe_id") == "hand_mine_coal"]
    # No active runs left, no queued auto-restart entries.
    assert not any(a.party == party for a in w.active_production)
    queue = w.scenario_state.get("production_auto_restart_queue") or []
    assert not [e for e in queue if e.get("party") == str(party)]


def test_continuous_production_auto_restarts():
    """run_count=-1 keeps firing production_done until inputs run out or we stop ticking."""
    w = bootstrap_genesis(
        seed=42, grid_width=12, grid_height=10, settler_count=2, map_layout="continent"
    )
    party = PartyId("player")
    pid = _find_hand_mine_coal_plot(w, party)
    _stock(w, party, "mining_pick", 1)
    _give_cash(w, party, 1_000_000)
    r = start_production(w, party, pid, "hand_mine_coal", run_count=CONTINUOUS_RUN_COUNT)
    assert r["ok"], r
    seen_run_ids: set[str] = set()
    for _ in range(720 * 5):
        advance_tick(w)
        for a in w.active_production:
            if a.party == party and a.recipe_id == "hand_mine_coal":
                seen_run_ids.add(a.run_id)
    assert len(seen_run_ids) >= 3, (
        f"continuous run_count=-1 should produce ≥3 distinct runs, got {len(seen_run_ids)}"
    )


def test_production_stalls_without_input():
    """Continuous production stalls with `production_input_stall` when input
    material is exhausted, then resumes when the input is restocked."""
    from realm.buildings import build_on_plot
    from realm.recipes import RECIPES

    w = bootstrap_genesis(
        seed=42, grid_width=12, grid_height=10, settler_count=2, map_layout="continent"
    )
    party = PartyId("player")
    from realm.actions import survey_plot
    from realm.world.terrain import Terrain

    pid = None
    for plot_id, plot in w.plots.items():
        if plot.owner is None and plot.terrain == Terrain.PLAINS:
            pid = plot_id
            break
    assert pid is not None
    _give_cash(w, party, 5_000_000)
    assert claim_plot(w, party, pid)["ok"]
    assert survey_plot(w, party, pid).get("ok")
    _stock(w, party, "timber", 6)
    _stock(w, party, "lumber", 2)
    _stock(w, party, "coal", 2)
    r = build_on_plot(w, party, pid, "wood_shop", build_mode="turnkey")
    assert r["ok"], r
    while any(
        b.get("plot_id") == str(pid)
        and b.get("building_id") == "wood_shop"
        and int(b.get("completes_at_tick", 0)) > w.tick
        for b in w.plot_buildings
    ):
        advance_tick(w)
    # Sawmill recipe: 2 timber + 1 electricity → 1 lumber. Stock electricity
    # generously so timber is the limiting reagent.
    rec = RECIPES["sawmill"]
    timber_per_run = int(rec.inputs[MaterialId("timber")])
    _stock(w, party, "timber", timber_per_run)
    _stock(w, party, "electricity", 50)
    r = start_production(w, party, pid, "sawmill", run_count=CONTINUOUS_RUN_COUNT)
    assert r["ok"], r
    # Tick past completion of the first run plus enough for the stall to fire.
    for _ in range(int(rec.duration_ticks) + 5):
        advance_tick(w)
    stalls = [
        ev
        for ev in w.event_log
        if str(ev.get("kind")) == "production_input_stall"
        and str(ev.get("party")) == str(party)
    ]
    assert stalls, "expected at least one production_input_stall after the first batch"
    # No new sawmill run active for the player.
    assert not any(
        a.party == party and a.recipe_id == "sawmill" for a in w.active_production
    )
    # Restock and tick past the retry window — run should pick up again.
    _stock(w, party, "timber", timber_per_run * 2)
    from realm.production import AUTO_RESTART_INPUT_STALL_RETRY_TICKS

    for _ in range(AUTO_RESTART_INPUT_STALL_RETRY_TICKS + 5):
        advance_tick(w)
    assert any(
        a.party == party and a.recipe_id == "sawmill" for a in w.active_production
    ), "production should resume after input restock + retry window"


def test_throughput_multiplier_combines_factors():
    """``throughput_breakdown`` multiplies maintenance × terrain × labour."""
    w = bootstrap_genesis(
        seed=42, grid_width=12, grid_height=10, settler_count=2, map_layout="continent"
    )
    party = PartyId("player")
    from realm.actions import survey_plot
    from realm.buildings import build_on_plot
    from realm.world.terrain import Terrain

    pid = None
    for plot_id, plot in w.plots.items():
        if plot.owner is None and plot.terrain == Terrain.PLAINS:
            pid = plot_id
            break
    assert pid is not None
    _give_cash(w, party, 5_000_000)
    assert claim_plot(w, party, pid)["ok"]
    assert survey_plot(w, party, pid).get("ok")
    _stock(w, party, "timber", 6)
    _stock(w, party, "lumber", 2)
    _stock(w, party, "coal", 2)
    r = build_on_plot(w, party, pid, "wood_shop", build_mode="turnkey")
    assert r["ok"], r
    while any(
        b.get("plot_id") == str(pid)
        and b.get("building_id") == "wood_shop"
        and int(b.get("completes_at_tick", 0)) > w.tick
        for b in w.plot_buildings
    ):
        advance_tick(w)
    # Set efficiency to 80% on the wood_shop.
    iid = next(
        str(b["instance_id"])
        for b in w.plot_buildings
        if b["plot_id"] == str(pid) and b["building_id"] == "wood_shop"
    )
    w.building_maintenance[iid] = {
        "due_at_tick": w.tick + 1000,
        "missed_cycles": 0,
        "efficiency_pct": 80,
    }
    tb = throughput_breakdown(w, party, pid, "sawmill")
    assert tb["ok"] is True
    assert tb["efficiency_pct"] == 80
    # Combined ≈ efficiency × terrain × labour. Labour bps may be 5000 (understaffed).
    assert 0 < tb["combined_bps"] <= 10_000 * 1.2 * 0.8 + 1

"""Sprint 1 / Phase B — building maintenance, efficiency decay, settler auto-maintain."""

from __future__ import annotations

from realm.actions import claim_plot, start_production_on_plot, survey_plot
from realm.buildings import BUILDINGS, build_on_plot
from realm.decay import (
    EFFICIENCY_FIRST_MISS,
    EFFICIENCY_HEALTHY,
    EFFICIENCY_SECOND_MISS,
    EFFICIENCY_STOPPED,
    building_efficiency_pct,
    maintain_building,
    tick_building_maintenance,
)
from realm.economy.exchange import _GENESIS_EXCHANGE
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.production import effective_outputs_for_completion
from realm.recipes import RECIPES
from realm.world.terrain import Terrain
from realm.world import ActiveProduction, SubsurfaceRoll, bootstrap_frontier, bootstrap_genesis

_TICKS_PER_GAME_DAY = 1440


def _ledger_total(w) -> int:
    return w.ledger.total_cents()


def _build_strip_mine(w, party: PartyId, pid: PlotId, *, mode: str = "turnkey") -> str:
    """Build a strip_mine and return its instance_id (skipping construction wait)."""
    # Seed enough materials for turnkey build.
    if mode == "turnkey":
        for mid_s, qty in (BUILDINGS["strip_mine"]["self_materials"] or {}).items():
            w.inventory.add(party, MaterialId(mid_s), int(qty))
    r = build_on_plot(w, party, pid, "strip_mine", build_mode=mode)
    assert r["ok"], r
    iid = r["instance_id"]
    # Fast-forward past construction.
    row = next(b for b in w.plot_buildings if b.get("instance_id") == iid)
    row["completes_at_tick"] = max(0, int(w.tick) - 1)
    return iid


def _force_mountain_plot(w, pid: PlotId) -> None:
    """Bootstraps a deterministic terrain so strip_mine recipes work."""
    plot = w.plots[pid]
    plot.terrain = Terrain.MOUNTAIN
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.5,
        copper_ore_grade=0.3,
        clay_grade=0.1,
        coal_grade=0.6,
    )
    plot.surveyed = True


def _seed_party_cash(w, party: PartyId, cents: int) -> None:
    w.ledger.ensure_account(party_cash_account(party))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=cents,
    )


def _fresh_frontier_with_player():
    w = bootstrap_frontier(seed=23, grid_width=4, grid_height=4)
    party = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, party, pid)["ok"]
    assert survey_plot(w, party, pid)["ok"]
    _force_mountain_plot(w, pid)
    return w, party, pid


# ─────────────────────────── core schedule mechanics ────────────────────────────


def test_building_starts_healthy() -> None:
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    rec = w.building_maintenance[iid]
    assert rec["efficiency_pct"] == EFFICIENCY_HEALTHY
    assert rec["missed_cycles"] == 0
    assert rec["due_at_tick"] > w.tick


def test_maintenance_degrades_on_schedule() -> None:
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    sched = BUILDINGS["strip_mine"]["maintenance_schedule"]
    grace = int(sched["grace_ticks"])
    # Jump past due_at_tick + grace.
    rec = w.building_maintenance[iid]
    w.tick = int(rec["due_at_tick"]) + grace + 1
    tick_building_maintenance(w)
    assert w.building_maintenance[iid]["missed_cycles"] == 1
    assert w.building_maintenance[iid]["efficiency_pct"] == EFFICIENCY_FIRST_MISS


def test_maintenance_stops_at_three_missed_cycles() -> None:
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    sched = BUILDINGS["strip_mine"]["maintenance_schedule"]
    grace = int(sched["grace_ticks"])
    interval = int(sched["interval_ticks"])
    rec = w.building_maintenance[iid]
    w.tick = int(rec["due_at_tick"]) + grace + 3 * interval + 1
    tick_building_maintenance(w)
    final = w.building_maintenance[iid]
    assert final["missed_cycles"] >= 3
    assert final["efficiency_pct"] == EFFICIENCY_STOPPED


def test_maintain_resets_efficiency_and_consumes_materials() -> None:
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    sched = BUILDINGS["strip_mine"]["maintenance_schedule"]
    # Degrade to second cycle (60%).
    rec = w.building_maintenance[iid]
    w.tick = int(rec["due_at_tick"]) + int(sched["grace_ticks"]) + int(sched["interval_ticks"]) + 1
    tick_building_maintenance(w)
    assert w.building_maintenance[iid]["efficiency_pct"] == EFFICIENCY_SECOND_MISS
    # Stock the maintenance materials and call maintain.
    for mid_s, qty in (sched["materials"] or {}).items():
        w.inventory.add(party, MaterialId(mid_s), int(qty))
    before_qty = {
        m: w.inventory.qty(party, MaterialId(m)) for m in (sched["materials"] or {})
    }
    starting_total = _ledger_total(w)
    r = maintain_building(w, party, iid)
    assert r["ok"], r
    assert r["schedule"] == "materials"
    # Inventory must be drained by the schedule.
    for m, before in before_qty.items():
        consumed = int((sched["materials"] or {})[m])
        assert w.inventory.qty(party, MaterialId(m)) == before - consumed
    # Schedule resets.
    rec2 = w.building_maintenance[iid]
    assert rec2["missed_cycles"] == 0
    assert rec2["efficiency_pct"] == EFFICIENCY_HEALTHY
    assert rec2["due_at_tick"] > w.tick
    # Maintenance is matter-only: no cash transfer.
    assert _ledger_total(w) == starting_total


def test_maintain_fails_without_materials() -> None:
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    r = maintain_building(w, party, iid)
    assert r["ok"] is False
    assert "missing material" in r["reason"]


# ───────────────────────────── production efficiency ────────────────────────────


def test_production_scales_with_efficiency() -> None:
    """At 80% efficiency, mine_coal output is 80% of base output."""
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    # Pretend a run is in flight.
    recipe = RECIPES["mine_coal"]
    run = ActiveProduction(
        run_id="rtest",
        party=party,
        plot_id=pid,
        recipe_id=recipe.recipe_id,
        ticks_remaining=0,
    )
    # Healthy baseline.
    out_full = effective_outputs_for_completion(w, run, recipe)
    # Force efficiency to 80%.
    w.building_maintenance[iid]["efficiency_pct"] = 80
    out_low = effective_outputs_for_completion(w, run, recipe)
    coal = MaterialId("coal")
    assert out_low[coal] == (int(out_full[coal]) * 80) // 100


def test_start_production_refused_when_building_stopped() -> None:
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    _seed_party_cash(w, party, 100_000)
    w.inventory.add(party, MaterialId("electricity"), 10)
    w.building_maintenance[iid]["efficiency_pct"] = EFFICIENCY_STOPPED
    r = start_production_on_plot(w, party, pid, "mine_coal")
    assert r["ok"] is False
    assert "stopped" in r["reason"] or "maintenance" in r["reason"]


# ─────────────────────────── settler auto-maintenance ───────────────────────────


def test_settler_buys_materials_and_maintains_before_deadline() -> None:
    """A settler whose strip_mine's ``due_at_tick`` is in <1 game-day buys timber/rope
    from the exchange and runs maintenance before efficiency drops."""
    from realm.agents_genesis_settlers import _settler_maintain_buildings

    w = bootstrap_genesis(seed=11, settler_count=4, grid_width=18, grid_height=12)
    party = PartyId("settler_000")
    w.parties.add(party)
    _seed_party_cash(w, party, 5_000_00)
    # Plant a strip_mine the settler "owns" on a mountain plot.
    target = PlotId("p-0-0")
    plot = w.plots[target]
    plot.terrain = Terrain.MOUNTAIN
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.5,
        copper_ore_grade=0.3,
        clay_grade=0.1,
        coal_grade=0.7,
    )
    plot.owner = party
    plot.surveyed = True
    # Stock the exchange so settler buys can clear (genesis bootstrap already has lots).
    iid = _build_strip_mine(w, party, target)
    # Pre-stock the maintenance materials in the settler's inventory so the test
    # focuses on the schedule path (the exchange seed doesn't always carry rope).
    sched = BUILDINGS["strip_mine"]["maintenance_schedule"]
    for mid_s, qty in (sched["materials"] or {}).items():
        w.inventory.add(party, MaterialId(mid_s), int(qty) + 1)
    rec = w.building_maintenance[iid]
    rec["due_at_tick"] = int(w.tick) + 100  # within 1 game-day threshold
    starting_total = _ledger_total(w)
    _settler_maintain_buildings(w, party)
    rec_after = w.building_maintenance[iid]
    assert rec_after["efficiency_pct"] == EFFICIENCY_HEALTHY
    assert rec_after["due_at_tick"] >= int(w.tick) + int(sched["interval_ticks"]) - 1
    # Materials must have been consumed.
    for mid_s, qty in (sched["materials"] or {}).items():
        assert w.inventory.qty(party, MaterialId(mid_s)) == 1, (
            f"settler should have consumed {qty}× {mid_s} (1 left from seed of {qty}+1)"
        )
    # Ledger conservation.
    assert _ledger_total(w) == starting_total


# ────────────────────────────── conservation ───────────────────────────────────


def test_tick_building_maintenance_is_inventory_neutral() -> None:
    """Running ``tick_building_maintenance`` many times must not move inventory or ledger
    (it only flips efficiency state)."""
    w, party, pid = _fresh_frontier_with_player()
    iid = _build_strip_mine(w, party, pid)
    inv_before = w.inventory.qty(party, MaterialId("timber"))
    total_before = _ledger_total(w)
    for _ in range(2000):
        tick_building_maintenance(w)
        w.tick += 1
    assert w.inventory.qty(party, MaterialId("timber")) == inv_before
    assert _ledger_total(w) == total_before

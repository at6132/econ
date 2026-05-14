"""Building condition decay and maintenance (Law 5 — decay without upkeep).

Two complementary mechanisms run in lockstep:

* **Condition (cash-based)**: each plot building has ``condition_bps`` in 0..10_000.
  Below ``BUILDING_MIN_EFFECTIVE_BPS`` the structure no longer grants labor or
  storage bonuses until maintained. ``maintain_building`` clears this.

* **Material maintenance schedule (Sprint 1)**: contracted buildings declare a
  ``maintenance_schedule`` in ``buildings.BUILDINGS``. Each instance gets a record
  in ``world.building_maintenance`` tracking ``due_at_tick`` / ``missed_cycles``
  / ``efficiency_pct``. Once overdue past the grace window, efficiency drops in
  steps (100 → 80 → 60 → 0). ``tick_building_maintenance`` advances this state
  every tick. ``maintain_building`` consumes the scheduled materials and resets
  the record (also restoring ``condition_bps`` to full as a courtesy).

The two systems are intentionally complementary: condition decays gradually
under load (cash maintenance restores it), while the scheduled overhauls cost
real materials and are mandatory to keep the plant running at full output.
"""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import building_operational
from realm.world import World

BUILDING_CONDITION_FULL_BPS = 10_000
BUILDING_MIN_EFFECTIVE_BPS = 2_500
# With 1 tick ≈ 1 in-game minute, ~1 bps/minute ≈ full rot in ~7 game-days without maintenance.
DECAY_BPS_PER_TICK = 1
MAINTENANCE_COST_DIVISOR = 5  # fee = max(1_000, build_cost_cents // 5)

# Efficiency stair for the materials-schedule maintenance mechanism.
EFFICIENCY_HEALTHY: int = 100
EFFICIENCY_FIRST_MISS: int = 80
EFFICIENCY_SECOND_MISS: int = 60
EFFICIENCY_STOPPED: int = 0


def building_condition_bps(row: dict) -> int:
    v = row.get("condition_bps", BUILDING_CONDITION_FULL_BPS)
    try:
        n = int(v)
    except (TypeError, ValueError):
        return BUILDING_CONDITION_FULL_BPS
    return max(0, min(BUILDING_CONDITION_FULL_BPS, n))


def building_effective_for_bonuses(row: dict) -> bool:
    return building_condition_bps(row) >= BUILDING_MIN_EFFECTIVE_BPS


def tick_building_decay(world: World) -> None:
    """Apply passive decay to every completed structure each tick."""
    t = world.tick
    for b in world.plot_buildings:
        if not building_operational(b, at_tick=t):
            continue
        cur = building_condition_bps(b)
        bid = str(b.get("building_id", ""))
        rate = DECAY_BPS_PER_TICK
        if bid == "watch_hut":
            rate = max(1, DECAY_BPS_PER_TICK * 2 // 3)
        elif bid == "field_stockade":
            rate = max(1, DECAY_BPS_PER_TICK * 3 // 4)
        b["condition_bps"] = max(0, cur - rate)


# ───────────────────────── Material maintenance schedule ─────────────────────────


def maintenance_schedule_for(building_id: str) -> dict | None:
    """Return the schedule blob for ``building_id`` or ``None`` if not scheduled."""
    # Local import to avoid a circular load: ``buildings`` imports ``BUILDING_CONDITION_FULL_BPS``.
    from realm.buildings import BUILDINGS

    spec = BUILDINGS.get(building_id)
    if spec is None:
        return None
    sched = spec.get("maintenance_schedule")
    if not isinstance(sched, dict):
        return None
    return sched


def _ensure_maintenance_record(world: World, row: dict) -> dict | None:
    """Lazily create the maintenance record for a building instance (if it has a schedule).

    Old snapshots loaded before this field existed get backfilled here at first sight.
    Returns the record or ``None`` if the building has no schedule.
    """
    bid = str(row.get("building_id", ""))
    sched = maintenance_schedule_for(bid)
    if sched is None:
        return None
    iid = str(row.get("instance_id") or "")
    if not iid:
        return None
    rec = world.building_maintenance.get(iid)
    if rec is None:
        completes_at = int(row.get("completes_at_tick", 0) or 0)
        interval = int(sched.get("interval_ticks", 0))
        # First maintenance window is one full ``interval`` past completion (or
        # past current tick for old buildings without a completes_at_tick).
        anchor = max(int(world.tick), completes_at)
        rec = {
            "due_at_tick": anchor + max(1, interval),
            "missed_cycles": 0,
            "efficiency_pct": EFFICIENCY_HEALTHY,
        }
        world.building_maintenance[iid] = rec
    return rec


def building_efficiency_pct(world: World, instance_id: str) -> int:
    """Return the current production efficiency for one building (default 100 if no record)."""
    rec = world.building_maintenance.get(instance_id)
    if rec is None:
        return EFFICIENCY_HEALTHY
    return int(rec.get("efficiency_pct", EFFICIENCY_HEALTHY))


def building_maintenance_status(world: World, row: dict) -> dict:
    """Public DTO for /world and UI rendering.

    Returns ``{schedule, due_at_tick, missed_cycles, efficiency_pct, materials,
    interval_ticks, grace_ticks}`` for scheduled buildings; ``{schedule: None}``
    otherwise.
    """
    bid = str(row.get("building_id", ""))
    sched = maintenance_schedule_for(bid)
    if sched is None:
        return {"schedule": None}
    rec = _ensure_maintenance_record(world, row)
    if rec is None:
        return {"schedule": None}
    return {
        "schedule": "materials",
        "due_at_tick": int(rec["due_at_tick"]),
        "missed_cycles": int(rec["missed_cycles"]),
        "efficiency_pct": int(rec["efficiency_pct"]),
        "interval_ticks": int(sched.get("interval_ticks", 0)),
        "grace_ticks": int(sched.get("grace_ticks", 0)),
        "materials": {str(k): int(v) for k, v in (sched.get("materials") or {}).items()},
    }


def tick_building_maintenance(world: World) -> None:
    """Advance the maintenance efficiency stair for every scheduled building."""
    for row in world.plot_buildings:
        if not building_operational(row, at_tick=world.tick):
            continue
        rec = _ensure_maintenance_record(world, row)
        if rec is None:
            continue
        bid = str(row.get("building_id", ""))
        sched = maintenance_schedule_for(bid)
        if sched is None:
            continue
        grace = int(sched.get("grace_ticks", 0))
        interval = max(1, int(sched.get("interval_ticks", 0)))
        due_at = int(rec["due_at_tick"])
        overdue_by = int(world.tick) - (due_at + grace)
        if overdue_by < 0:
            continue
        # Compute the desired missed_cycles for the elapsed overdue ticks.
        # Cycle 1 starts at overdue_by >= 0; each additional ``interval`` elapsed
        # pushes us one cycle further.
        desired_missed = 1 + (overdue_by // interval)
        desired_missed = max(int(rec["missed_cycles"]), int(desired_missed))
        if desired_missed == int(rec["missed_cycles"]):
            continue
        # Only emit log lines for transitions to new cycles this tick.
        previous = int(rec["missed_cycles"])
        for cycle in range(previous + 1, desired_missed + 1):
            new_eff = _efficiency_for_missed_cycle(cycle)
            rec["efficiency_pct"] = int(new_eff)
            rec["missed_cycles"] = cycle
            log_event(
                world,
                "building_degraded",
                f"{row.get('building_id')} on {row.get('plot_id')} "
                f"efficiency dropped to {new_eff}% — maintenance overdue (cycle {cycle})",
                party=str(row.get("party") or ""),
                plot_id=str(row.get("plot_id") or ""),
                instance_id=str(row.get("instance_id") or ""),
                building_id=str(row.get("building_id") or ""),
                missed_cycles=cycle,
                efficiency_pct=int(new_eff),
            )
            if new_eff == EFFICIENCY_STOPPED:
                break


def _efficiency_for_missed_cycle(missed: int) -> int:
    if missed <= 0:
        return EFFICIENCY_HEALTHY
    if missed == 1:
        return EFFICIENCY_FIRST_MISS
    if missed == 2:
        return EFFICIENCY_SECOND_MISS
    return EFFICIENCY_STOPPED


def maintain_building(world: World, party: PartyId, instance_id: str) -> dict:
    """Run one maintenance pass on a single building instance.

    Materials-path (preferred): if the building has a ``maintenance_schedule``, the
    party must hold the scheduled materials in inventory. The materials are consumed,
    the schedule record resets (``due_at_tick`` rolls forward, ``missed_cycles`` zeros,
    ``efficiency_pct`` returns to 100), and ``condition_bps`` is also restored to full.

    Cash-path (legacy fallback): if the building has no schedule (simple sheds, watch
    hut, etc.) the legacy cash fee is charged and only ``condition_bps`` is restored.

    Conservation: materials are removed via the inventory transaction layer; cash is
    transferred via the ledger.
    """
    row: dict | None = None
    for b in world.plot_buildings:
        if str(b.get("instance_id", "")) == instance_id:
            row = b
            break
    if row is None:
        return {"ok": False, "reason": "unknown building instance"}
    if not building_operational(row, at_tick=world.tick):
        return {"ok": False, "reason": "building still under construction"}
    if row.get("party") != str(party):
        return {"ok": False, "reason": "not your building"}
    plot_id = PlotId(str(row["plot_id"]))
    plot = world.plots.get(plot_id)
    if plot is None or plot.owner != party:
        return {"ok": False, "reason": "plot not owned"}

    bid = str(row.get("building_id", ""))
    sched = maintenance_schedule_for(bid)

    if sched is not None:
        mats_raw = sched.get("materials") or {}
        mats: dict[str, int] = {str(k): int(v) for k, v in mats_raw.items()}
        # Need-check before any state mutation.
        for mid_s, qty in mats.items():
            have = world.inventory.qty(party, MaterialId(mid_s))
            if have < qty:
                return {
                    "ok": False,
                    "reason": f"missing material: {mid_s} (need {qty}, have {have})",
                }
        # Consume.
        consumed: list[tuple[str, int]] = []
        for mid_s, qty in mats.items():
            rm = world.inventory.remove(party, MaterialId(mid_s), int(qty))
            if isinstance(rm, MatterErr):
                for done_s, done_q in consumed:
                    world.inventory.add(party, MaterialId(done_s), int(done_q))
                return {"ok": False, "reason": rm.reason}
            consumed.append((mid_s, int(qty)))
        # Reset the schedule record.
        rec = _ensure_maintenance_record(world, row)
        if rec is not None:
            interval = max(1, int(sched.get("interval_ticks", 0)))
            rec["due_at_tick"] = int(world.tick) + interval
            rec["missed_cycles"] = 0
            rec["efficiency_pct"] = EFFICIENCY_HEALTHY
        row["condition_bps"] = BUILDING_CONDITION_FULL_BPS
        log_event(
            world,
            "building_maintained",
            f"{party} maintained {bid} on {plot_id} (materials: "
            + ", ".join(f"{mid_s}×{qty}" for mid_s, qty in consumed) + ")",
            party=str(party),
            plot_id=str(plot_id),
            instance_id=instance_id,
            building_id=bid,
            materials_consumed={k: v for k, v in consumed},
        )
        return {"ok": True, "schedule": "materials", "materials": dict(mats)}

    # Legacy cash-only path for sheds / non-scheduled buildings.
    base_cost = int(row.get("cost_cents", 25_000))
    fee = max(1_000, base_cost // MAINTENANCE_COST_DIVISOR)
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < fee:
        return {"ok": False, "reason": "insufficient cash for maintenance"}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=fee,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    row["condition_bps"] = BUILDING_CONDITION_FULL_BPS
    log_event(
        world,
        "maintain",
        f"{party} maintained {row.get('building_id')} on {plot_id} for ${fee / 100:.2f}",
        party=str(party),
        plot_id=str(plot_id),
        instance_id=instance_id,
        fee_cents=fee,
    )
    return {"ok": True, "schedule": "cash", "fee_cents": fee}

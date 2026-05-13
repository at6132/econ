"""Production runs: inputs consumed at start, outputs + tick countdown (Primitive 6)."""

from __future__ import annotations

from realm.decay import building_effective_for_bonuses
from realm.event_log import log_event
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.plot_logistics import (
    PLOT_OUTPUT_STORAGE_CAP_UNITS,
    plot_output_qty,
    plot_output_total,
    remove_plot_output,
    try_add_plot_output,
    uses_plot_logistics,
)
from realm.recipe_workshops import plot_has_workshop_for_recipe
from realm.recipe_sites import recipe_allowed_on_terrain, subsurface_allows_recipe, terrain_allows_workshop
from realm.recipes import RECIPES
from realm.storage_caps import party_inventory_unit_total, party_storage_cap_units, try_add_inventory
from realm.time_scale import building_operational
from realm.world import ActiveProduction, World

# Basis points: share of recipe labor paid out to hired workers (rest + remainder → system reserve).
EMPLOYMENT_LABOR_TO_WORKERS_BPS = 4000  # 40%

# Recipe labor multiplier when producing on a plot with workshop / logistics buildings.
TOOL_CACHE_LABOR_BPS = 9000  # −10% cash labor vs recipe
WATCH_HUT_LABOR_BPS = 9700  # −3%


def _min_grade_for_field(recipe, field: str) -> float:
    for f, mn in recipe.requires_subsurface:
        if f == field:
            return float(mn)
    return 0.3


def scale_extraction_output_qty(base: int, grade: float, min_grade: float) -> int:
    """Higher subsurface grade → more units (deterministic; same plot → same scale)."""
    if base <= 0:
        return 0
    g = max(0.0, min(1.0, float(grade)))
    mn = max(1e-9, float(min_grade))
    if g < mn:
        return base
    span = max(1e-9, 1.0 - mn)
    t = min(1.0, max(0.0, (g - mn) / span))
    extra = int(round(base * 2 * t))
    return max(base, min(base * 4, base + extra))


def effective_outputs_for_completion(world: World, run: ActiveProduction, recipe) -> dict[MaterialId, int]:
    plot = world.plots.get(run.plot_id)
    out = {k: int(v) for k, v in recipe.outputs.items()}
    if recipe.scaled_output is None or plot is None:
        return out
    field, mid = recipe.scaled_output
    if mid not in out:
        return out
    grade = float(getattr(plot.subsurface, field, 0.0))
    mn = _min_grade_for_field(recipe, field)
    out[mid] = scale_extraction_output_qty(out[mid], grade, mn)
    return out


def _plot_owned_by(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


def _active_on_plot(world: World, plot_id: PlotId) -> bool:
    return any(a.plot_id == plot_id for a in world.active_production)


def plot_has_active_production(world: World, plot_id: PlotId) -> bool:
    """True if any in-flight batch is running on this plot."""
    return _active_on_plot(world, plot_id)


def active_production_on_plot(world: World, plot_id: PlotId) -> ActiveProduction | None:
    """The active run on ``plot_id``, if any (any party — plot should be singly owned)."""
    for a in world.active_production:
        if a.plot_id == plot_id:
            return a
    return None


def _labor_bps_for_plot(world: World, party: PartyId, plot_id: PlotId) -> int:
    """Lowest (best for player) labor BPS among buildings on this plot."""
    bps = 10_000
    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("plot_id") != str(plot_id):
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if not building_effective_for_bonuses(b):
            continue
        bid = b.get("building_id")
        if bid == "tool_cache":
            bps = min(bps, TOOL_CACHE_LABOR_BPS)
        elif bid == "watch_hut":
            bps = min(bps, WATCH_HUT_LABOR_BPS)
    return bps


def _rollback_consumed_inputs(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    consumed_inv: dict[MaterialId, int],
    consumed_plot: dict[MaterialId, int],
) -> None:
    for mid, q in consumed_inv.items():
        world.inventory.add(party, mid, q)
    for mid, q in consumed_plot.items():
        rb = try_add_plot_output(world, plot_id, party, mid, q)
        if isinstance(rb, MatterErr):
            raise RuntimeError(f"rollback plot stash failed: {rb.reason}")


def _distinct_employees_for_employer(world: World, employer: PartyId) -> list[PartyId]:
    seen: set[str] = set()
    out: list[PartyId] = []
    for h in world.stub_hires:
        if h.get("employer") != str(employer):
            continue
        e = str(h.get("employee", ""))
        if e and e not in seen:
            seen.add(e)
            out.append(PartyId(e))
    return out


def _pay_recipe_labor(
    world: World, party: PartyId, recipe_labor_cents: int
) -> MoneyErr | None:
    """
    Pay recipe labor from employer cash. With stub hires, split part to employees; rest to reserve.
    Returns MoneyErr on failure (caller rolls back inputs).
    """
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < recipe_labor_cents:
        return MoneyErr(reason="insufficient cash for labor")
    employees = _distinct_employees_for_employer(world, party)
    if not employees:
        pay = world.ledger.transfer(
            debit=cash,
            credit=system_reserve_account(),
            amount_cents=recipe_labor_cents,
        )
        return pay if isinstance(pay, MoneyErr) else None
    worker_pool = recipe_labor_cents * EMPLOYMENT_LABOR_TO_WORKERS_BPS // 10_000
    to_reserve = recipe_labor_cents - worker_pool
    n = len(employees)
    per = worker_pool // n
    remainder = worker_pool - per * n
    to_reserve += remainder
    paid: list[tuple[PartyId, int]] = []
    for emp in employees:
        if per <= 0:
            continue
        ec = party_cash_account(emp)
        tr = world.ledger.transfer(debit=cash, credit=ec, amount_cents=per)
        if isinstance(tr, MoneyErr):
            for emp2, amt in paid:
                world.ledger.transfer(debit=party_cash_account(emp2), credit=cash, amount_cents=amt)
            return tr
        paid.append((emp, per))
    if to_reserve > 0:
        tr2 = world.ledger.transfer(
            debit=cash,
            credit=system_reserve_account(),
            amount_cents=to_reserve,
        )
        if isinstance(tr2, MoneyErr):
            for emp2, amt in paid:
                world.ledger.transfer(debit=party_cash_account(emp2), credit=cash, amount_cents=amt)
            return tr2
    return None


def start_production(world: World, party: PartyId, plot_id: PlotId, recipe_id: str) -> dict:
    """
    Start one batch: consumes inputs + labor (cash) immediately; delivers outputs after duration.

    On success: ``{ok: True, started: True, run_id, recipe_id, plot_id, ticks_remaining,
    completes_at_tick, message}``.

    If a batch is already running on this plot: ``{ok: True, started: False, status: "active", ...}``
    (no state change). Failures: ``{ok: False, reason}``.

    ``completes_at_tick`` is ``world.tick + ticks_remaining`` (approximate; storage stalls extend it).
    """
    if not _plot_owned_by(world, party, plot_id):
        return {"ok": False, "reason": "plot not owned"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if not plot.surveyed:
        return {"ok": False, "reason": "plot not surveyed"}
    if not terrain_allows_workshop(plot.terrain):
        return {"ok": False, "reason": "cannot produce on water"}
    active = active_production_on_plot(world, plot_id)
    if active is not None:
        ct = int(world.tick) + int(active.ticks_remaining)
        return {
            "ok": True,
            "started": False,
            "status": "active",
            "run_id": active.run_id,
            "recipe_id": active.recipe_id,
            "plot_id": str(plot_id),
            "ticks_remaining": int(active.ticks_remaining),
            "completes_at_tick": ct,
            "message": (
                f"Production already in progress ({active.recipe_id} on {plot_id}); "
                f"completes around tick {ct}."
            ),
        }
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return {"ok": False, "reason": "unknown recipe"}
    if not recipe_allowed_on_terrain(plot.terrain, recipe_id):
        return {"ok": False, "reason": "recipe not available on this plot"}
    if not plot_has_workshop_for_recipe(world, party, plot_id, recipe_id):
        req = recipe.requires_building_id
        return {"ok": False, "reason": f"missing workshop: {req}"}
    if not subsurface_allows_recipe(plot, recipe):
        return {"ok": False, "reason": "subsurface below threshold for this recipe"}
    labor_bps = _labor_bps_for_plot(world, party, plot_id)
    labor_cents = recipe.labor_cents * labor_bps // 10_000
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < labor_cents:
        return {"ok": False, "reason": "insufficient cash for labor"}
    consumed_inv: dict[MaterialId, int] = {}
    consumed_plot: dict[MaterialId, int] = {}
    for mid, qty in recipe.inputs.items():
        inv_q = world.inventory.qty(party, mid)
        if uses_plot_logistics(world, party):
            if inv_q + plot_output_qty(world, plot_id, mid) < qty:
                return {"ok": False, "reason": f"insufficient {mid}"}
        elif inv_q < qty:
            return {"ok": False, "reason": f"insufficient {mid}"}
    for mid, qty in recipe.inputs.items():
        need = int(qty)
        take_inv = min(need, world.inventory.qty(party, mid))
        if take_inv > 0:
            rm = world.inventory.remove(party, mid, take_inv)
            if isinstance(rm, MatterErr):
                _rollback_consumed_inputs(world, party, plot_id, consumed_inv, consumed_plot)
                return {"ok": False, "reason": rm.reason}
            consumed_inv[mid] = consumed_inv.get(mid, 0) + take_inv
        need -= take_inv
        if need > 0:
            if not uses_plot_logistics(world, party):
                _rollback_consumed_inputs(world, party, plot_id, consumed_inv, consumed_plot)
                return {"ok": False, "reason": f"insufficient {mid}"}
            r2 = remove_plot_output(world, party, plot_id, mid, need)
            if isinstance(r2, MatterErr):
                _rollback_consumed_inputs(world, party, plot_id, consumed_inv, consumed_plot)
                return {"ok": False, "reason": r2.reason}
            consumed_plot[mid] = consumed_plot.get(mid, 0) + need
    labor_err = _pay_recipe_labor(world, party, labor_cents)
    if labor_err is not None:
        _rollback_consumed_inputs(world, party, plot_id, consumed_inv, consumed_plot)
        return {"ok": False, "reason": labor_err.reason}
    world.next_production_seq += 1
    run_id = f"run-{world.next_production_seq}"
    world.active_production.append(
        ActiveProduction(
            run_id=run_id,
            party=party,
            plot_id=plot_id,
            recipe_id=recipe_id,
            ticks_remaining=recipe.duration_ticks,
        )
    )
    log_event(
        world,
        "production_start",
        f"{party} started {recipe_id} on {plot_id} (outputs in {recipe.duration_ticks} ticks; labor {labor_bps / 100:.1f}% of recipe)",
        party=str(party),
        plot_id=str(plot_id),
        recipe_id=recipe_id,
        run_id=run_id,
        labor_bps=labor_bps,
    )
    ct = int(world.tick) + int(recipe.duration_ticks)
    return {
        "ok": True,
        "started": True,
        "run_id": run_id,
        "recipe_id": recipe_id,
        "plot_id": str(plot_id),
        "ticks_remaining": int(recipe.duration_ticks),
        "completes_at_tick": ct,
        "message": f"Started {recipe_id}; outputs due around tick {ct}.",
    }


def tick_production(world: World) -> None:
    """Advance all active runs; complete finished batches."""
    still: list[ActiveProduction] = []
    for run in world.active_production:
        run.ticks_remaining -= 1
        if run.ticks_remaining > 0:
            still.append(run)
            continue
        recipe = RECIPES.get(run.recipe_id)
        if recipe is None:
            continue
        eff_out = effective_outputs_for_completion(world, run, recipe)
        out_total = sum(eff_out.values())
        if uses_plot_logistics(world, run.party):
            if plot_output_total(world, run.plot_id) + out_total > PLOT_OUTPUT_STORAGE_CAP_UNITS:
                run.ticks_remaining = 1
                still.append(run)
                log_event(
                    world,
                    "production_stalled_storage",
                    f"{run.party} plot stash full for {recipe.recipe_id} outputs — retry next tick",
                    party=str(run.party),
                    plot_id=str(run.plot_id),
                    recipe_id=run.recipe_id,
                    run_id=run.run_id,
                )
                continue
            staged_plot: list[tuple[MaterialId, int]] = []
            blocked_plot = False
            for mid, qty in eff_out.items():
                ad = try_add_plot_output(world, run.plot_id, run.party, mid, qty)
                if isinstance(ad, MatterErr):
                    blocked_plot = True
                    break
                staged_plot.append((mid, qty))
            if blocked_plot:
                for mid, qty in staged_plot:
                    remove_plot_output(world, run.party, run.plot_id, mid, qty)
                run.ticks_remaining = 1
                still.append(run)
                log_event(
                    world,
                    "production_stalled_storage",
                    f"{run.party} plot output blocked for {recipe.recipe_id} — retry next tick",
                    party=str(run.party),
                    plot_id=str(run.plot_id),
                    recipe_id=run.recipe_id,
                    run_id=run.run_id,
                )
                continue
        elif party_inventory_unit_total(world, run.party) + out_total > party_storage_cap_units(
            world, run.party
        ):
            run.ticks_remaining = 1
            still.append(run)
            log_event(
                world,
                "production_stalled_storage",
                f"{run.party} cannot take {recipe.recipe_id} outputs (storage full) — retry next tick",
                party=str(run.party),
                plot_id=str(run.plot_id),
                recipe_id=run.recipe_id,
                run_id=run.run_id,
            )
            continue
        if not uses_plot_logistics(world, run.party):
            staged: list[tuple[MaterialId, int]] = []
            blocked = False
            for mid, qty in eff_out.items():
                ad = try_add_inventory(world, run.party, mid, qty)
                if isinstance(ad, MatterErr):
                    blocked = True
                    break
                staged.append((mid, qty))
            if blocked:
                for mid, qty in staged:
                    world.inventory.remove(run.party, mid, qty)
                run.ticks_remaining = 1
                still.append(run)
                log_event(
                    world,
                    "production_stalled_storage",
                    f"{run.party} output blocked for {recipe.recipe_id} — retry next tick",
                    party=str(run.party),
                    plot_id=str(run.plot_id),
                    recipe_id=run.recipe_id,
                    run_id=run.run_id,
                )
                continue
        log_event(
            world,
            "production_done",
            f"{run.party} finished {run.recipe_id} on {run.plot_id}",
            party=str(run.party),
            plot_id=str(run.plot_id),
            recipe_id=run.recipe_id,
            run_id=run.run_id,
        )
    world.active_production = still

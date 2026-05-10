"""Production runs: inputs consumed at start, outputs + tick countdown (Primitive 6)."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.recipes import RECIPES
from realm.world import ActiveProduction, World

# Basis points: share of recipe labor paid out to hired workers (rest + remainder → system reserve).
EMPLOYMENT_LABOR_TO_WORKERS_BPS = 4000  # 40%


def _plot_owned_by(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


def _active_on_plot(world: World, plot_id: PlotId) -> bool:
    return any(a.plot_id == plot_id for a in world.active_production)


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

    Returns {ok: True, run_id} | {ok: False, reason}.
    """
    if not _plot_owned_by(world, party, plot_id):
        return {"ok": False, "reason": "plot not owned"}
    if _active_on_plot(world, plot_id):
        return {"ok": False, "reason": "plot already has active production"}
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return {"ok": False, "reason": "unknown recipe"}
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < recipe.labor_cents:
        return {"ok": False, "reason": "insufficient cash for labor"}
    for mid, qty in recipe.inputs.items():
        if world.inventory.qty(party, mid) < qty:
            return {"ok": False, "reason": f"insufficient {mid}"}
    for mid, qty in recipe.inputs.items():
        rm = world.inventory.remove(party, mid, qty)
        if isinstance(rm, MatterErr):
            return {"ok": False, "reason": rm.reason}
    labor_err = _pay_recipe_labor(world, party, recipe.labor_cents)
    if labor_err is not None:
        for mid, qty in recipe.inputs.items():
            world.inventory.add(party, mid, qty)
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
        f"{party} started {recipe_id} on {plot_id} (outputs in {recipe.duration_ticks} ticks)",
        party=str(party),
        plot_id=str(plot_id),
        recipe_id=recipe_id,
        run_id=run_id,
    )
    return {"ok": True, "run_id": run_id}


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
        for mid, qty in recipe.outputs.items():
            ad = world.inventory.add(run.party, mid, qty)
            if isinstance(ad, MatterErr):
                # should not happen for positive qty
                pass
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


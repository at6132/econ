"""Production runs: inputs consumed at start, outputs + tick countdown (Primitive 6)."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.recipes import RECIPES
from realm.world import ActiveProduction, World


def _plot_owned_by(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


def _active_on_plot(world: World, plot_id: PlotId) -> bool:
    return any(a.plot_id == plot_id for a in world.active_production)


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
    pay = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=recipe.labor_cents,
    )
    if isinstance(pay, MoneyErr):
        # rollback inputs (best-effort)
        for mid, qty in recipe.inputs.items():
            world.inventory.add(party, mid, qty)
        return {"ok": False, "reason": pay.reason}
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


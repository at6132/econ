"""Production runs: inputs consumed at start, outputs + tick countdown (Primitive 6)."""

from __future__ import annotations

from realm.production.decay import (
    EFFICIENCY_HEALTHY,
    EFFICIENCY_STOPPED,
    building_effective_for_bonuses,
    building_efficiency_pct,
)
from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import (
    AccountId,
    MoneyErr,
    party_cash_account,
    system_reserve_account,
)
from realm.infrastructure.plot_logistics import (
    PLOT_OUTPUT_STORAGE_CAP_UNITS,
    plot_output_qty,
    plot_output_total,
    remove_plot_output,
    try_add_plot_output,
    uses_plot_logistics,
)
from realm.production.recipe_workshops import plot_has_workshop_for_recipe
from realm.production.recipe_sites import (
    recipe_allowed_on_plot,
    recipe_allowed_on_terrain,
    recipe_terrain_bonus_bps,
    subsurface_allows_recipe,
    terrain_allows_workshop,
)
from realm.production.recipes import RECIPES
from realm.production.storage_caps import party_inventory_unit_total, party_storage_cap_units, try_add_inventory
from realm.core.time_scale import building_operational
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


def _workshop_efficiency_pct_for_run(world: World, run: ActiveProduction, recipe) -> int:
    """Lookup ``efficiency_pct`` for the workshop building this run uses.

    Returns 100 for hand recipes (no workshop) and for buildings without a
    scheduled maintenance record. When multiple matching buildings exist on the
    plot (uncommon), the lowest efficiency wins — the spec scales output by the
    weakest link.
    """
    if recipe.requires_tool is not None:
        return EFFICIENCY_HEALTHY
    req = recipe.requires_building_id
    if not req:
        return EFFICIENCY_HEALTHY
    best = EFFICIENCY_HEALTHY
    found = False
    for b in world.plot_buildings:
        if b.get("party") != str(run.party) or b.get("plot_id") != str(run.plot_id):
            continue
        if b.get("building_id") != req:
            continue
        iid = str(b.get("instance_id") or "")
        if not iid:
            continue
        pct = building_efficiency_pct(world, iid)
        if not found or pct < best:
            best = pct
            found = True
    return best if found else EFFICIENCY_HEALTHY


def effective_outputs_for_completion(world: World, run: ActiveProduction, recipe) -> dict[MaterialId, int]:
    plot = world.plots.get(run.plot_id)
    out = {k: int(v) for k, v in recipe.outputs.items()}
    if plot is not None and recipe.scaled_output is not None:
        field, mid = recipe.scaled_output
        if mid in out:
            grade = float(getattr(plot.subsurface, field, 0.0))
            mn = _min_grade_for_field(recipe, field)
            out[mid] = scale_extraction_output_qty(out[mid], grade, mn)
    # Per-terrain output bonus (e.g. mountain ore +20%). Applied before maintenance
    # scaling so the bonus survives a degraded plant proportionally.
    if plot is not None:
        bps = recipe_terrain_bonus_bps(recipe.recipe_id, plot.terrain)
        if bps != 10_000:
            out = {k: max(0, (int(v) * int(bps)) // 10_000) for k, v in out.items()}
    # Apply maintenance efficiency last so degraded plants produce proportionally less.
    eff = _workshop_efficiency_pct_for_run(world, run, recipe)
    if eff != EFFICIENCY_HEALTHY:
        out = {k: max(0, (int(v) * int(eff)) // 100) for k, v in out.items()}
    # Sprint 3 — Phase C.2: labour staffing modifier.
    #   - No hired workers + recipe demands labour  → 50 % output (understaffed).
    #   - Hired workers                              → 100 %.
    #   - Hired skilled workers                      → up to 120 %.
    if int(getattr(recipe, "labor_cents", 0)) > 0:
        from realm.population.labor import effective_output_bps_for_run

        labour_bps = effective_output_bps_for_run(
            world, run.party, has_recipe_labor=True
        )
        if labour_bps != 10_000:
            out = {k: max(0, (int(v) * int(labour_bps)) // 10_000) for k, v in out.items()}
    # Phase 8 — Sub-phase 8A: seasonal yield modifier composes multiplicatively
    # on top of all the above. Winter ``grow_grain`` returns 0 (recipe is also
    # blocked at start-time on non-tropical islands). Autumn harvest window
    # surges to 1.5×; winter timber chops at 0.6×; northern fishing freezes.
    from realm.events.seasons import yield_modifier

    season_mod = yield_modifier(world, recipe.recipe_id, plot)
    if season_mod != 1.0:
        out = {k: max(0, int(round(int(v) * float(season_mod)))) for k, v in out.items()}
    # Phase 8 — Sub-phase 8B: active world events (drought, blight, flood)
    # compose on top of the seasonal multiplier. Drought reduces output
    # proportionally; blight zeros the affected recipe; flood blocks ground
    # recipes on flooded plots.
    from realm.events.world_events import yield_modifier_for_plot

    event_mod = yield_modifier_for_plot(world, recipe.recipe_id, plot)
    if event_mod != 1.0:
        out = {k: max(0, int(round(int(v) * float(event_mod)))) for k, v in out.items()}
    # Phase 8 — Sub-phase 8D: resource depletion. Mining recipes draw down
    # the relevant subsurface grade by a tiny amount per completion (handled
    # at the run-completion site in ``_apply_subsurface_depletion`` below,
    # not here — output is computed BEFORE the depletion charge so a single
    # run sees the pre-depletion grade).
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


def _find_local_laborer_for_wage(
    world: World, plot_id: PlotId, employer: PartyId
) -> "LaborerNPC | None":
    """Phase 9C — pick a deterministic real laborer to receive the recipe wage.

    Preference order (closer to the workplace and not already engaged):

      1. Laborers whose ``home_town`` is on the same island as the plot AND
         whose ``employer`` is the requesting party or unset.
      2. Same-island laborers regardless of employer (including unemployed).
      3. Anyone with a ``home_town`` (cross-island fallback).

    Selection within each tier is deterministic (sort by laborer_id, then
    advance via a stable rotation index so the same employer doesn't always
    pay the same person). Returns ``None`` if the world has no housed
    laborers — caller falls back to system:reserve in that frontier case.
    """
    from realm.population.laborers import LaborerNPC

    laborers = list(world.laborers.values())
    if not laborers:
        return None
    plot = world.plots.get(plot_id)
    if plot is None:
        return None
    plot_islands = world.scenario_state.get("plot_islands") or {}
    plot_island_raw = plot_islands.get(str(plot_id))
    target_island = int(plot_island_raw) if plot_island_raw is not None else None

    def _housed(lab: LaborerNPC) -> bool:
        return lab.home_town is not None

    same_island_friendly: list[LaborerNPC] = []
    same_island_any: list[LaborerNPC] = []
    other_housed: list[LaborerNPC] = []
    for lab in laborers:
        if not _housed(lab):
            continue
        if target_island is not None and int(lab.island_id) == target_island:
            same_island_any.append(lab)
            if lab.employer is None or lab.employer == employer:
                same_island_friendly.append(lab)
        else:
            other_housed.append(lab)
    tier = (
        same_island_friendly
        if same_island_friendly
        else same_island_any
        if same_island_any
        else other_housed
    )
    if not tier:
        return None
    tier.sort(key=lambda lab: lab.laborer_id)
    # Rotation index keeps the same employer from always paying the same person.
    rotation = world.scenario_state.setdefault("wage_rotation", {})
    key = f"{employer}|{target_island}"
    idx = int(rotation.get(key, 0)) % len(tier)
    rotation[key] = idx + 1
    return tier[idx]


def _credit_real_laborer_or_reserve(
    world: World,
    plot_id: PlotId,
    employer: PartyId,
    debit_account: AccountId,
    amount_cents: int,
) -> MoneyErr | None:
    """Credit a real laborer's cash account when one is reachable, else fall
    back to ``system:reserve`` (genuinely frontier — no housed population on
    or near the plot). Updates the laborer's ``cash_cents`` mirror so the
    next ``tick_laborer_spending`` cycle sees the new balance.
    """
    if amount_cents <= 0:
        return None
    lab = _find_local_laborer_for_wage(world, plot_id, employer)
    if lab is None:
        return _ensure_money_err(
            world.ledger.transfer(
                debit=debit_account,
                credit=system_reserve_account(),
                amount_cents=amount_cents,
            )
        )
    from realm.population.laborers import laborer_cash_account

    acct = laborer_cash_account(lab.laborer_id)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=debit_account, credit=acct, amount_cents=amount_cents
    )
    if isinstance(tr, MoneyErr):
        return tr
    lab.cash_cents = world.ledger.balance(acct)
    log_event(
        world,
        "laborer_wage_paid",
        f"{employer} paid laborer {lab.laborer_id} ${amount_cents / 100:.2f} for work on {plot_id}",
        employer=str(employer),
        laborer_id=lab.laborer_id,
        plot_id=str(plot_id),
        amount_cents=int(amount_cents),
    )
    return None


def _ensure_money_err(res) -> MoneyErr | None:
    return res if isinstance(res, MoneyErr) else None


def _pay_recipe_labor(
    world: World,
    party: PartyId,
    recipe_labor_cents: int,
    plot_id: PlotId,
) -> MoneyErr | None:
    """
    Pay recipe labor from employer cash. Phase 9C: instead of sinking the
    leftover to ``system:reserve``, route it to a real local laborer so the
    money stays in the consumer economy. With ``stub_hires`` employees we
    split per existing rules and still re-route the residual.
    """
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < recipe_labor_cents:
        return MoneyErr(reason="insufficient cash for labor")
    employees = _distinct_employees_for_employer(world, party)
    if not employees:
        return _credit_real_laborer_or_reserve(
            world, plot_id, party, cash, recipe_labor_cents
        )
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
        err = _credit_real_laborer_or_reserve(
            world, plot_id, party, cash, to_reserve
        )
        if err is not None:
            for emp2, amt in paid:
                world.ledger.transfer(
                    debit=party_cash_account(emp2), credit=cash, amount_cents=amt
                )
            return err
    return None


CONTINUOUS_RUN_COUNT: int = -1
"""Sentinel for ``start_production(run_count=-1)`` — keep restarting until the
workshop degrades or inputs disappear."""

# Phase 9F — tool wear. Probability (in bps) that a hand-tool recipe breaks
# its required tool on production-start. 250 bps = 2.5 % per run. Tools cost
# $20-$35 to buy and a hand-mine_ore recipe nets ~$200 of ore, so the wear
# rate adds a small but visible recurring cost (~$0.50 per recipe on average).
TOOL_WEAR_BREAK_BPS: int = 250

MIN_EFFICIENCY_FOR_AUTO_RESTART: int = 60
"""Auto-restart stops once efficiency drops below this percent."""

AUTO_RESTART_INPUT_STALL_RETRY_TICKS: int = 60


def start_production(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    recipe_id: str,
    run_count: int = 1,
) -> dict:
    """
    Start one batch: consumes inputs + labor (cash) immediately; delivers outputs after duration.

    ``run_count``:
      - ``1`` (default) — single batch, current behaviour.
      - ``> 1`` — start one batch now and queue ``run_count - 1`` more runs to
        auto-restart sequentially after each ``production_done``.
      - ``-1`` (``CONTINUOUS_RUN_COUNT``) — auto-restart continuously until the
        workshop degrades below 60% efficiency, inputs run out, or the player
        cancels.

    Auto-restart attempts to begin the next run immediately on completion; on
    insufficient input it emits ``production_input_stall`` and retries every
    ``AUTO_RESTART_INPUT_STALL_RETRY_TICKS`` ticks via ``tick_production_auto_restart``.

    On success: ``{ok: True, started: True, run_id, recipe_id, plot_id, ticks_remaining,
    completes_at_tick, runs_remaining, message}``.

    If a batch is already running on this plot: ``{ok: True, started: False, status: "active", ...}``
    (no state change). Failures: ``{ok: False, reason}``.

    ``completes_at_tick`` is ``world.tick + ticks_remaining`` (approximate; storage stalls extend it).
    """
    rc = int(run_count)
    if rc == 0 or rc < -1:
        return {"ok": False, "reason": "run_count must be -1 (continuous) or >= 1"}
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
    if not world.can_party_run_recipe(party, recipe_id):
        return {"ok": False, "reason": "recipe not yet discovered"}
    plot_ok, plot_reason = recipe_allowed_on_plot(world, plot, recipe_id)
    if not plot_ok:
        return {"ok": False, "reason": plot_reason or "recipe not available on this plot"}
    if recipe.requires_tool is not None:
        tool = recipe.requires_tool
        if world.inventory.qty(party, tool) < 1:
            return {"ok": False, "reason": f"missing tool: {tool}"}
        # Phase 9F — tool wear (Law 5). Each hand-tool recipe rolls
        # against TOOL_WEAR_BREAK_BPS; on hit the tool is consumed and the
        # event is logged so the player notices the recurring cost. The
        # purpose key bakes in tick + plot so two simultaneous recipes don't
        # share an RNG draw.
        wear_rng = world.rng(f"tool_wear|{world.tick}|{recipe_id}|{plot_id}")
        if wear_rng.randint(0, 9_999) < TOOL_WEAR_BREAK_BPS:
            rm_tool = world.inventory.remove(party, tool, 1)
            if not isinstance(rm_tool, MatterErr):
                log_event(
                    world,
                    "tool_wear_broke",
                    f"{party}'s {tool} broke during {recipe_id} on {plot_id}",
                    party=str(party),
                    plot_id=str(plot_id),
                    recipe_id=recipe_id,
                    tool=str(tool),
                )
    elif not plot_has_workshop_for_recipe(world, party, plot_id, recipe_id):
        req = recipe.requires_building_id
        return {"ok": False, "reason": f"missing workshop: {req}"}
    else:
        # Refuse to start when the workshop is at 0% efficiency — the building has stopped.
        req = recipe.requires_building_id
        stopped = False
        for b in world.plot_buildings:
            if (
                b.get("party") == str(party)
                and b.get("plot_id") == str(plot_id)
                and b.get("building_id") == req
            ):
                iid = str(b.get("instance_id") or "")
                if iid and building_efficiency_pct(world, iid) == EFFICIENCY_STOPPED:
                    stopped = True
                    break
        if stopped:
            return {"ok": False, "reason": "building stopped — maintenance required"}
    if not subsurface_allows_recipe(plot, recipe):
        return {"ok": False, "reason": "subsurface below threshold for this recipe"}
    # Phase 8 — Sub-phase 8A: refuse to start recipes whose seasonal modifier is
    # zero (e.g. ``grow_grain`` in winter on non-tropical islands, ``fishing``
    # in winter on northern islands). Recipes with a reduced but non-zero
    # seasonal multiplier are still allowed to start — they just produce less.
    from realm.events.seasons import recipe_blocked_by_season

    blocked, season_reason = recipe_blocked_by_season(world, recipe_id, plot)
    if blocked:
        return {"ok": False, "reason": season_reason}
    # Phase 8 — Sub-phase 8B: refuse to start recipes that an active world
    # event (drought, blight, flood) has zeroed for this plot.
    from realm.events.world_events import recipe_blocked_by_active_event

    ev_blocked, ev_reason = recipe_blocked_by_active_event(world, recipe_id, plot)
    if ev_blocked:
        return {"ok": False, "reason": ev_reason}
    # Sprint 3 — Phase A: electricity-requiring recipes need either a grid
    # source within coverage or staged electricity to draw from.
    electricity_mid = MaterialId("electricity")
    needs_electricity = int(recipe.inputs.get(electricity_mid, 0)) > 0
    powered_by_grid = False
    if needs_electricity:
        from realm.infrastructure.energy import is_plot_powered

        powered_by_grid = is_plot_powered(world, plot_id)
        if not powered_by_grid:
            inv_e = world.inventory.qty(party, electricity_mid)
            if inv_e < int(recipe.inputs[electricity_mid]):
                return {
                    "ok": False,
                    "reason": (
                        "no power source within range — build a power_shed or ship electricity"
                    ),
                }
    labor_bps = _labor_bps_for_plot(world, party, plot_id)
    labor_cents = recipe.labor_cents * labor_bps // 10_000
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < labor_cents:
        return {"ok": False, "reason": "insufficient cash for labor"}
    consumed_inv: dict[MaterialId, int] = {}
    consumed_plot: dict[MaterialId, int] = {}
    # When the plot sits on the energy grid, the electricity input is satisfied
    # by the grid (the power_shed's owner ate the fuel cost). Skip that material
    # in both the precondition check and the consumption loop.
    def _is_waived_input(material: MaterialId) -> bool:
        return needs_electricity and powered_by_grid and material == electricity_mid

    for mid, qty in recipe.inputs.items():
        if _is_waived_input(mid):
            continue
        if world.inventory.qty(party, mid) < qty:
            return {"ok": False, "reason": f"insufficient {mid}"}
    for mid, qty in recipe.inputs.items():
        if _is_waived_input(mid):
            continue
        rm = world.inventory.remove(party, mid, int(qty))
        if isinstance(rm, MatterErr):
            _rollback_consumed_inputs(world, party, plot_id, consumed_inv, consumed_plot)
            return {"ok": False, "reason": rm.reason}
        consumed_inv[mid] = consumed_inv.get(mid, 0) + int(qty)
    labor_err = _pay_recipe_labor(world, party, labor_cents, plot_id)
    if labor_err is not None:
        _rollback_consumed_inputs(world, party, plot_id, consumed_inv, consumed_plot)
        return {"ok": False, "reason": labor_err.reason}
    world.next_production_seq += 1
    run_id = f"run-{world.next_production_seq}"
    # runs_remaining = additional runs to queue after this one.
    if rc == CONTINUOUS_RUN_COUNT:
        queued = CONTINUOUS_RUN_COUNT
    else:
        queued = max(0, rc - 1)
    world.active_production.append(
        ActiveProduction(
            run_id=run_id,
            party=party,
            plot_id=plot_id,
            recipe_id=recipe_id,
            ticks_remaining=recipe.duration_ticks,
            runs_remaining=queued,
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
        "runs_remaining": int(queued),
        "message": f"Started {recipe_id}; outputs due around tick {ct}.",
    }


def tick_production(world: World) -> None:
    """Advance all active runs; complete finished batches.

    Auto-restart (Sprint 6 Phase B) is deferred until after the completion
    loop so the newly-started run doesn't see the completed run still sitting
    in ``world.active_production`` (which would short-circuit it as "active").
    """
    still: list[ActiveProduction] = []
    completed_for_auto_restart: list[ActiveProduction] = []
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
        # Sprint 6 — Phase D.1: production output always goes to party inventory
        # (the source of truth for matter). When ``use_plot_output_logistics``
        # is set the same qty is *also* recorded in ``plot_output_stock`` as a
        # cumulative per-plot display log — but plot_output_stock is no longer
        # treated as matter storage.
        if party_inventory_unit_total(world, run.party) + out_total > party_storage_cap_units(
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
        # Cumulative display log: plot_output_stock records what was produced
        # on this plot, even though the matter now lives in inventory.
        if world.use_plot_output_logistics:
            bucket = world.plot_output_stock.setdefault(str(run.plot_id), {})
            for mid, qty in eff_out.items():
                bucket[str(mid)] = int(bucket.get(str(mid), 0)) + int(qty)
        log_event(
            world,
            "production_done",
            f"{run.party} finished {run.recipe_id} on {run.plot_id}",
            party=str(run.party),
            plot_id=str(run.plot_id),
            recipe_id=run.recipe_id,
            run_id=run.run_id,
        )
        # Phase 8 — Sub-phase 8D: resource depletion. Mining recipes draw down
        # the relevant subsurface grade by a tiny amount per completion (a
        # ``mine_ore`` run at 100% efficiency depletes the grade by 0.001;
        # ~500 runs takes a healthy plot below the recipe's min_grade gate).
        _apply_subsurface_depletion(world, run, recipe)
        # Sprint 6 — Phase D.2: optional auto-listing of fresh output.
        if eff_out:
            _maybe_auto_list_outputs(world, run, eff_out)
        # Sprint 6 — Phase B: auto-restart is deferred until after the loop
        # so the new ActiveProduction doesn't collide with the completed one.
        if run.runs_remaining != 0:
            completed_for_auto_restart.append(run)
        # Sprint 3 — Phase C.3: every worker that participated levels up once.
        if int(getattr(recipe, "labor_cents", 0)) > 0:
            from realm.population.labor import increment_worker_skill

            increment_worker_skill(world, run.party, by=1)
        if str(run.recipe_id).startswith("hand_") and world.scenario_id == "genesis":
            gst = world.scenario_state.setdefault("genesis", {})
            gst["hand_tier0_completions"] = int(gst.get("hand_tier0_completions", 0)) + 1
        # Sprint 2 / Phase B: feed the settler cost-basis tracker so future asks
        # reflect this party's actual input costs rather than the exchange's quote.
        if str(run.party).startswith("settler_") and world.scenario_id == "genesis":
            from realm.genesis.settler_cost_basis import record_settler_production

            for out_mid, out_qty in eff_out.items():
                record_settler_production(
                    world, run.party, run.recipe_id, out_mid, int(out_qty)
                )
    world.active_production = still
    for completed in completed_for_auto_restart:
        _maybe_schedule_auto_restart(world, completed)


# ────────────────────────────────────────────────────────────────────────
# Phase 8 — Sub-phase 8D: resource depletion
# ────────────────────────────────────────────────────────────────────────


SUBSURFACE_DEPLETION_PER_RUN: float = 0.001
"""Per-run subsurface grade decrement at 100% efficiency. Scales linearly
with workshop efficiency_pct so a degraded plant depletes slower (it
extracts less). Tuned so a healthy plot at grade 0.80 stays viable for
~500 game-days of continuous mining before the recipe gate closes."""

DEPLETION_WARNING_GRADE: float = 0.35
"""Below this, the world feed emits a one-shot near-depletion warning."""

DEPLETION_FLOOR_GRADE: float = 0.30
"""Below this, the recipe's start-time min-grade gate refuses new runs."""


def _apply_subsurface_depletion(world: World, run: ActiveProduction, recipe) -> None:
    """Reduce the relevant subsurface grade on the run's plot.

    Mining recipes target ``recipe.scaled_output`` (the (field, material)
    tuple that says "this recipe scales output by ``plot.subsurface.<field>``").
    Non-extractive recipes have ``scaled_output is None`` and are skipped.

    Conservation note: subsurface grades are world-gen state, not matter or
    money. Depleting a grade does NOT affect ``world.ledger.total_cents``
    or ``world.inventory`` totals. The depletion model represents geological
    finiteness, which sits below the conservation invariants.
    """
    import dataclasses

    scaled = getattr(recipe, "scaled_output", None)
    if scaled is None:
        return
    field_name = scaled[0]
    plot = world.plots.get(run.plot_id)
    if plot is None:
        return
    sub = plot.subsurface
    current = float(getattr(sub, field_name, 0.0) or 0.0)
    if current <= 0.0:
        return
    eff = _workshop_efficiency_pct_for_run(world, run, recipe) or EFFICIENCY_HEALTHY
    decrement = SUBSURFACE_DEPLETION_PER_RUN * (eff / 100.0)
    new_val = max(0.0, current - decrement)
    # SubsurfaceRoll is frozen — rebuild via dataclasses.replace.
    plot.subsurface = dataclasses.replace(sub, **{field_name: new_val})
    # One-shot warning when the grade crosses the warning threshold.
    if current >= DEPLETION_WARNING_GRADE > new_val:
        log_event(
            world,
            "world_feed",
            f"Survey data indicates {field_name.replace('_', ' ')} deposit at {run.plot_id} "
            f"is approaching depletion. Grade currently at {new_val:.2f}.",
            event_class="depletion_warning",
            plot_id=str(run.plot_id),
            field=field_name,
            grade=round(new_val, 4),
        )
    # Exhaustion (recipe gate closes at min_grade = 0.30 for most extracts).
    if current >= DEPLETION_FLOOR_GRADE > new_val:
        log_event(
            world,
            "world_feed",
            f"The {field_name.replace('_', ' ')} deposit at {run.plot_id} has been exhausted. "
            f"Mining is no longer viable here.",
            event_class="depletion_exhausted",
            plot_id=str(run.plot_id),
            field=field_name,
            grade=round(new_val, 4),
        )


# ────────────────────────────────────────────────────────────────────────
# Sprint 6 — Phase D.2: auto-list output
# ────────────────────────────────────────────────────────────────────────

AUTO_LIST_MARGIN_BPS: int = 13_000
"""Auto-list target = ``cost_basis × 1.30`` (30 % margin)."""


def _building_for_run(world: World, run: ActiveProduction) -> dict | None:
    """The first matching ``plot_buildings`` row this run is using, if any.

    Hand recipes have no workshop; this returns ``None``.
    """
    recipe = RECIPES.get(run.recipe_id)
    if recipe is None or not recipe.requires_building_id:
        return None
    req = recipe.requires_building_id
    for b in world.plot_buildings:
        if b.get("party") != str(run.party):
            continue
        if b.get("plot_id") != str(run.plot_id):
            continue
        if b.get("building_id") == req:
            return b
    return None


def _auto_list_price_cents(world: World, material: MaterialId) -> int | None:
    """Auto-list price = cost basis × 1.30, falling back through cost-basis sources.

    Returns ``None`` only if no priceable basis exists for the material.
    """
    try:
        from realm.economy.pricing import (
            producer_cost_basis_cents,
            settler_cost_basis_cents,
            _FAIR_VALUE_CENTS,
        )
    except Exception:
        return None
    basis = producer_cost_basis_cents(material)
    if basis is None:
        basis = settler_cost_basis_cents(material)
    if basis is None:
        fv = _FAIR_VALUE_CENTS.get(str(material))
        if fv is None:
            return None
        basis = int(fv)
    return max(1, (int(basis) * AUTO_LIST_MARGIN_BPS + 9_999) // 10_000)


def _maybe_auto_list_outputs(
    world: World, run: ActiveProduction, eff_out: dict[MaterialId, int]
) -> None:
    """If the building has ``auto_list_output: True``, list each output material
    at ``cost_basis × 1.30`` from the party's inventory.

    Hand recipes are skipped (no workshop row to flag).
    """
    b = _building_for_run(world, run)
    if b is None or not bool(b.get("auto_list_output")):
        return
    from realm.economy.markets import place_sell_order

    for mid, qty in eff_out.items():
        q = int(qty)
        if q <= 0:
            continue
        if world.inventory.qty(run.party, mid) < q:
            continue
        price = _auto_list_price_cents(world, mid)
        if price is None:
            continue
        place_sell_order(world, run.party, mid, q, price)


def set_building_auto_list(
    world: World, party: PartyId, instance_id: str, enabled: bool
) -> dict:
    """Toggle ``auto_list_output`` for a building owned by ``party``.

    Players opt-in per workshop. The flag persists in the building row and
    is consulted on every ``production_done``.
    """
    for b in world.plot_buildings:
        if str(b.get("instance_id") or "") != str(instance_id):
            continue
        if b.get("party") != str(party):
            return {"ok": False, "reason": "not owner"}
        b["auto_list_output"] = bool(enabled)
        log_event(
            world,
            "auto_list_toggled",
            f"{party} {'enabled' if enabled else 'disabled'} auto-list on {b.get('building_id')} ({instance_id})",
            party=str(party),
            building_id=str(b.get("building_id")),
            instance_id=str(instance_id),
            enabled=bool(enabled),
        )
        return {"ok": True, "enabled": bool(enabled)}
    return {"ok": False, "reason": "building not found"}


# ────────────────────────────────────────────────────────────────────────
# Sprint 6 — Phase B: auto-restart machinery
# ────────────────────────────────────────────────────────────────────────


def _auto_restart_queue(world: World) -> list[dict]:
    """Pending auto-restarts (stalls and queued counts).

    Each entry: ``{party, plot_id, recipe_id, runs_remaining, retry_at_tick}``.
    ``runs_remaining`` decrements per successful re-launch; ``-1`` = continuous.
    """
    return world.scenario_state.setdefault("production_auto_restart_queue", [])


def _maybe_schedule_auto_restart(world: World, run: ActiveProduction) -> None:
    """After a successful completion, queue the next run if the player asked for one.

    ``run.runs_remaining`` semantics: "additional runs to launch after this one".
    For run_count=3 (initial), the first ActiveProduction carries ``runs_remaining=2``.
    On its completion we need to launch a new ActiveProduction whose own
    ``runs_remaining=1`` — i.e. invoke ``start_production`` with ``run_count=2``.
    """
    if run.runs_remaining == 0:
        return
    # ``rc_for_next`` for ``start_production`` = total runs left including the
    # one we are about to launch.
    rc_for_next = (
        CONTINUOUS_RUN_COUNT
        if run.runs_remaining == CONTINUOUS_RUN_COUNT
        else int(run.runs_remaining)
    )
    next_remaining = rc_for_next
    if _workshop_below_auto_restart_threshold(world, run):
        log_event(
            world,
            "production_auto_restart_stopped",
            f"{run.party} auto-restart for {run.recipe_id} stopped (workshop below {MIN_EFFICIENCY_FOR_AUTO_RESTART}%)",
            party=str(run.party),
            plot_id=str(run.plot_id),
            recipe_id=run.recipe_id,
        )
        return
    res = start_production(
        world, run.party, run.plot_id, run.recipe_id, run_count=rc_for_next
    )
    if res.get("ok") and res.get("started"):
        return
    # Otherwise queue a retry. ``insufficient X`` covers the "input stall" case.
    reason = str(res.get("reason", "")) if not res.get("ok") else ""
    if reason.startswith("insufficient"):
        log_event(
            world,
            "production_input_stall",
            f"{run.party} {run.recipe_id} on {run.plot_id} stalled: {reason}",
            party=str(run.party),
            plot_id=str(run.plot_id),
            recipe_id=run.recipe_id,
            reason=reason,
        )
        _auto_restart_queue(world).append(
            {
                "party": str(run.party),
                "plot_id": str(run.plot_id),
                "recipe_id": str(run.recipe_id),
                "runs_remaining": int(next_remaining),
                "retry_at_tick": int(world.tick) + AUTO_RESTART_INPUT_STALL_RETRY_TICKS,
            }
        )


def _workshop_below_auto_restart_threshold(world: World, run: ActiveProduction) -> bool:
    """Return True when the workshop on this plot is at < 60% efficiency."""
    recipe = RECIPES.get(run.recipe_id)
    if recipe is None:
        return False
    req = recipe.requires_building_id
    if not req:
        return False
    for b in world.plot_buildings:
        if (
            b.get("party") == str(run.party)
            and b.get("plot_id") == str(run.plot_id)
            and b.get("building_id") == req
        ):
            iid = str(b.get("instance_id") or "")
            if iid:
                eff = building_efficiency_pct(world, iid)
                if int(eff) < MIN_EFFICIENCY_FOR_AUTO_RESTART:
                    return True
    return False


def tick_production_auto_restart(world: World) -> None:
    """Poll the auto-restart queue and try to start any entries whose
    ``retry_at_tick`` has elapsed.

    Queue entry ``runs_remaining`` here means total runs still owed including
    the one we want to start now — so we pass it straight to ``start_production``
    as ``run_count``.
    """
    q = _auto_restart_queue(world)
    if not q:
        return
    kept: list[dict] = []
    for entry in q:
        if int(entry.get("retry_at_tick", 0)) > int(world.tick):
            kept.append(entry)
            continue
        party = PartyId(str(entry.get("party", "")))
        plot_id = PlotId(str(entry.get("plot_id", "")))
        recipe_id = str(entry.get("recipe_id", ""))
        runs_remaining = int(entry.get("runs_remaining", 0))
        if runs_remaining == 0:
            continue
        rc_for_next = (
            CONTINUOUS_RUN_COUNT if runs_remaining == CONTINUOUS_RUN_COUNT else runs_remaining
        )
        res = start_production(world, party, plot_id, recipe_id, run_count=rc_for_next)
        if res.get("ok") and res.get("started"):
            continue
        # Still blocked — reschedule one more retry window.
        entry["retry_at_tick"] = int(world.tick) + AUTO_RESTART_INPUT_STALL_RETRY_TICKS
        kept.append(entry)
    world.scenario_state["production_auto_restart_queue"] = kept


# ────────────────────────────────────────────────────────────────────────
# Sprint 6 — Phase B3: throughput multiplier (UI display helper)
# ────────────────────────────────────────────────────────────────────────


def throughput_breakdown(
    world: World, party: PartyId, plot_id: PlotId, recipe_id: str
) -> dict:
    """Return the multiplicative factors that determine output magnitude.

    Useful for the UI "Efficiency" indicator. The individual factors are in
    basis points (10_000 = 100%). The combined value is the integer product
    divided down to a single ``bps`` number.
    """
    from realm.production.decay import EFFICIENCY_HEALTHY
    from realm.population.labor import effective_output_bps_for_run

    plot = world.plots.get(plot_id)
    recipe = RECIPES.get(recipe_id)
    if plot is None or recipe is None:
        return {"ok": False, "reason": "unknown plot or recipe"}
    # Maintenance efficiency (taken from the workshop instance if present).
    eff_pct = EFFICIENCY_HEALTHY
    req = recipe.requires_building_id
    if req:
        for b in world.plot_buildings:
            if (
                b.get("party") == str(party)
                and b.get("plot_id") == str(plot_id)
                and b.get("building_id") == req
            ):
                iid = str(b.get("instance_id") or "")
                if iid:
                    eff_pct = building_efficiency_pct(world, iid)
                    break
    # Terrain bonus.
    terrain_bps = recipe_terrain_bonus_bps(recipe_id, plot.terrain)
    # Labor multiplier — only meaningful for recipes that consume labour.
    labour_bps = 10_000
    if int(getattr(recipe, "labor_cents", 0)) > 0:
        labour_bps = effective_output_bps_for_run(
            world, party, has_recipe_labor=True
        )
    combined_bps = (
        int(eff_pct) * 100  # eff_pct is /100 → convert to /10_000
        * int(terrain_bps) // 10_000
        * int(labour_bps) // 10_000
    )
    return {
        "ok": True,
        "efficiency_pct": int(eff_pct),
        "terrain_bps": int(terrain_bps),
        "labour_bps": int(labour_bps),
        "combined_bps": int(combined_bps),
        "combined_pct": int(combined_bps) // 100,
    }

"""Employment actions: hire NPC stub workers, recurring wages, poach, transport.

Functions:
  * ``hire_catalog_public``           — UI: list of NPCs that accept hire
  * ``hire_worker_stub``              — pay signing bonus + register stub employment,
                                        or hire a :class:`~realm.population.laborers.LaborerNPC`
                                        onto a real payroll (Phase 7E).
  * ``fire_laborer``                  — release a hired laborer from payroll
  * ``tick_stub_employment``          — pay recurring wages each tick interval
  * ``poach_worker``                  — defect a worker to a new employer at +20% wage
  * ``request_labor_transport_action`` — schedule a regional labor transit
"""

from __future__ import annotations

from realm.actions._shared import ActionErr, ActionOk, ActionResult
from realm.core.ids import PartyId
from realm.core.ledger import MoneyErr, party_cash_account
from realm.events.event_log import log_event
from realm.population.laborers import laborer_cash_account
from realm.world import World

HIRABLE_NPCS: frozenset[PartyId] = frozenset(
    {
        PartyId("npc_grain_vendor"),
        PartyId("t1_timber_merchant"),
        PartyId("t1_lumber_buyer"),
        PartyId("t1_coal_vendor"),
        PartyId("t1_clay_vendor"),
        PartyId("t1_electricity_buyer"),
    }
)


def hire_catalog_public() -> list[dict[str, str | int]]:
    """Suggested signing bonuses for the hire panel (Phase 1 stub employment)."""
    return [
        {"party": "npc_grain_vendor", "role": "Grain wholesaler", "suggested_signing_cents": 100},
        {"party": "t1_timber_merchant", "role": "Timber merchant", "suggested_signing_cents": 200},
        {"party": "t1_lumber_buyer", "role": "Lumber buyer", "suggested_signing_cents": 200},
        {"party": "t1_coal_vendor", "role": "Coal yard", "suggested_signing_cents": 150},
        {"party": "t1_clay_vendor", "role": "Clay pit operator", "suggested_signing_cents": 150},
        {"party": "t1_electricity_buyer", "role": "Industrial power buyer", "suggested_signing_cents": 350},
    ]


def hire_worker_stub(
    world: World,
    employer: PartyId,
    employee: PartyId,
    signing_bonus_cents: int,
    *,
    wage_per_tick_cents: int = 0,
    wage_interval_ticks: int = 1,
    workers_count: int = 1,
) -> ActionResult:
    """
    Signing bonus to an NPC party; optional recurring wage every ``wage_interval_ticks``.

    **Deprecated for human labor:** prefer ``POST /jobs/openings`` (real job market)
    or hire a laborer id returned by ``GET /laborers`` — this path still accepts
    the six Tier-1 catalog NPCs for production-line labor routing.

    Sprint 3 — Phase C.2: the bonus is multiplied by the regional labor-scarcity
    factor (1.0 / 1.25 / 1.6) and the action is rejected if the employer's
    region pool can't supply ``workers_count`` (or in critical bands, the batch
    exceeds the per-action share cap).
    """
    laborer_id = str(employee)
    if laborer_id in world.laborers:
        if workers_count != 1:
            return ActionErr(
                ok=False,
                reason="workers_count must be 1 when hiring a LaborerNPC",
            )
        if signing_bonus_cents < 0:
            return ActionErr(ok=False, reason="signing bonus must be non-negative")
        if wage_per_tick_cents < 0:
            return ActionErr(ok=False, reason="wage_per_tick_cents must be non-negative")
        if wage_interval_ticks < 1:
            return ActionErr(ok=False, reason="wage_interval_ticks must be at least 1")
        if employer not in world.parties:
            return ActionErr(ok=False, reason="unknown party")
        lab = world.laborers[laborer_id]
        if lab.employer is not None:
            return ActionErr(ok=False, reason="laborer already employed")
        bc = party_cash_account(employer)
        lc = laborer_cash_account(laborer_id)
        world.ledger.ensure_account(bc)
        world.ledger.ensure_account(lc)
        if signing_bonus_cents > 0:
            tr = world.ledger.transfer(
                debit=bc, credit=lc, amount_cents=int(signing_bonus_cents)
            )
            if isinstance(tr, MoneyErr):
                return ActionErr(ok=False, reason=tr.reason)
        lab.employer = employer
        lab.employment_contract = None
        from realm.population.employment import DEFAULT_WAGE_PER_GAME_DAY_CENTS

        per_day = int(wage_per_tick_cents) * int(wage_interval_ticks)
        lab.wage_per_day_cents = (
            per_day if per_day > 0 else int(DEFAULT_WAGE_PER_GAME_DAY_CENTS)
        )
        lab.cash_cents = world.ledger.balance(lc)
        log_event(
            world,
            "laborer_hired",
            f"{employer} hired laborer {laborer_id} (bonus {signing_bonus_cents}¢)",
            employer=str(employer),
            laborer_id=laborer_id,
            signing_bonus_cents=int(signing_bonus_cents),
        )
        return ActionOk(ok=True)

    if signing_bonus_cents <= 0:
        return ActionErr(ok=False, reason="signing bonus must be positive")
    if wage_per_tick_cents < 0:
        return ActionErr(ok=False, reason="wage_per_tick_cents must be non-negative")
    if wage_interval_ticks < 1:
        return ActionErr(ok=False, reason="wage_interval_ticks must be at least 1")
    if workers_count < 1:
        return ActionErr(ok=False, reason="workers_count must be at least 1")
    if employee not in HIRABLE_NPCS:
        return ActionErr(
            ok=False,
            reason=(
                "not a hirable party — use a LaborerNPC id from GET /laborers "
                "or one of the catalog NPCs (GET /jobs/openings/catalog)"
            ),
        )
    if employer not in world.parties or employee not in world.parties:
        return ActionErr(ok=False, reason="unknown party")
    # Regional labor cost premium + pool draw (Sprint 3 — Phase C.2).
    # Skipped for Frontier and minimal testbeds where the labor market is
    # inactive (``labor_market_active`` returns False there).
    from realm.population.labor import (
        critical_hire_batch_cap,
        decrement_pool,
        hire_cost_multiplier_bps,
        increment_pool,
        labor_market_active,
        labor_pool_for_region,
        region_for_party_home,
    )

    region_id: str | None = None
    bonus_cents = signing_bonus_cents
    if labor_market_active(world):
        region_id = region_for_party_home(world, employer)
        if region_id is not None:
            region_pool_avail = labor_pool_for_region(world, region_id)
            if region_pool_avail < workers_count:
                return ActionErr(ok=False, reason="insufficient labor pool in your region")
            cap = critical_hire_batch_cap(world, region_id)
            if workers_count > cap:
                return ActionErr(
                    ok=False,
                    reason=f"region pool critical — single hire batch capped at {cap} worker(s)",
                )
            bps = hire_cost_multiplier_bps(world, region_id)
            bonus_cents = signing_bonus_cents * bps // 10_000
            if not decrement_pool(world, region_id, workers_count):
                return ActionErr(ok=False, reason="insufficient labor pool in your region")
    ec = party_cash_account(employer)
    wc = party_cash_account(employee)
    if world.ledger.balance(ec) < bonus_cents:
        if region_id is not None:
            increment_pool(world, region_id, workers_count)
        return ActionErr(ok=False, reason="insufficient cash")
    pay = world.ledger.transfer(
        debit=ec,
        credit=wc,
        amount_cents=bonus_cents,
    )
    if isinstance(pay, MoneyErr):
        if region_id is not None:
            from realm.population.labor import increment_pool as _restore_pool

            _restore_pool(world, region_id, workers_count)
        return ActionErr(ok=False, reason=pay.reason)
    world.next_contract_seq += 1
    cid = f"c-{world.next_contract_seq}"
    interval = max(1, wage_interval_ticks)
    world.contracts.append(
        {
            "id": cid,
            "party_a": str(employer),
            "party_b": str(employee),
            "kind": "employment",
            "status": "active",
            "signing_bonus_cents": bonus_cents,
            "wage_per_tick_cents": wage_per_tick_cents,
            "wage_interval_ticks": interval,
        }
    )
    world.stub_hires.append(
        {
            "employer": str(employer),
            "employee": str(employee),
            "signing_bonus_cents": bonus_cents,
            "contract_id": cid,
            "tick": world.tick,
            "wage_per_tick_cents": wage_per_tick_cents,
            "wage_interval_ticks": interval,
            "next_wage_tick": world.tick + interval if wage_per_tick_cents > 0 else -1,
            # Sprint 3 — Phase C: regional labor pool bookkeeping.
            "region_id": region_id or "",
            "workers_count": int(workers_count),
            "skill_level": 0,
        }
    )
    log_event(
        world,
        "hire",
        f"{employer} hired {employee} (employment {cid}, bonus ${signing_bonus_cents / 100:.2f}"
        + (f", wage {wage_per_tick_cents}¢ / {interval} ticks" if wage_per_tick_cents > 0 else "")
        + ")",
        employer=str(employer),
        employee=str(employee),
        signing_bonus_cents=signing_bonus_cents,
        contract_id=cid,
    )
    return ActionOk(ok=True)


def fire_laborer(world: World, employer: PartyId, laborer_id: str) -> ActionResult:
    """Release a hired laborer. Clears any linked job opening slot."""
    if laborer_id not in world.laborers:
        return ActionErr(ok=False, reason="unknown laborer")
    lab = world.laborers[laborer_id]
    if lab.employer != employer:
        return ActionErr(ok=False, reason="not your employee")
    if lab.employment_contract is not None:
        for op in world.job_openings:
            if op.opening_id == lab.employment_contract:
                op.filled_by = None
                break
    lab.employer = None
    lab.employment_contract = None
    lab.wage_per_day_cents = 0
    log_event(
        world,
        "laborer_fired",
        f"{employer} released laborer {laborer_id}",
        employer=str(employer),
        laborer_id=laborer_id,
    )
    return ActionOk(ok=True)


def tick_stub_employment(world: World) -> None:
    """Pay recurring stub wages when due (employer must have cash)."""
    for h in world.stub_hires:
        wage = int(h.get("wage_per_tick_cents", 0))
        if wage <= 0:
            continue
        nxt = int(h.get("next_wage_tick", -1))
        if nxt < 0 or world.tick < nxt:
            continue
        emp = PartyId(str(h["employer"]))
        wkr = PartyId(str(h["employee"]))
        if emp not in world.parties or wkr not in world.parties:
            continue
        interval = max(1, int(h.get("wage_interval_ticks", 1)))
        ec, wc = party_cash_account(emp), party_cash_account(wkr)
        if world.ledger.balance(ec) >= wage:
            tr = world.ledger.transfer(debit=ec, credit=wc, amount_cents=wage)
            if not isinstance(tr, MoneyErr):
                log_event(
                    world,
                    "employment_wage",
                    f"{emp} paid {wkr} ${wage / 100:.2f} wage",
                    employer=str(emp),
                    employee=str(wkr),
                    wage_cents=wage,
                )
        h["next_wage_tick"] = nxt + interval


def poach_worker(
    world: World,
    poacher: PartyId,
    worker_contract_id: str,
    new_wage_per_tick_cents: int,
) -> ActionResult:
    """Sprint 3 — Phase C.3: offer a skilled worker a higher wage to defect.

    The new wage must be at least 20 % above the worker's current wage. Skill
    level moves with the worker. The poacher is charged a small signing bonus
    equal to the wage premium so poaching has a non-trivial cost.
    """
    if new_wage_per_tick_cents <= 0:
        return ActionErr(ok=False, reason="new wage must be positive")
    target: dict | None = None
    for h in world.stub_hires:
        if str(h.get("contract_id") or "") == worker_contract_id:
            target = h
            break
    if target is None:
        return ActionErr(ok=False, reason="unknown worker contract")
    cur_wage = int(target.get("wage_per_tick_cents", 0))
    if new_wage_per_tick_cents < int(cur_wage * 12) // 10:
        return ActionErr(
            ok=False,
            reason="poach offer must be ≥ 20 % above current wage",
        )
    employee = PartyId(str(target.get("employee") or ""))
    if employee not in world.parties:
        return ActionErr(ok=False, reason="employee unknown")
    bonus = max(1, new_wage_per_tick_cents - cur_wage)
    pc = party_cash_account(poacher)
    if world.ledger.balance(pc) < bonus:
        return ActionErr(ok=False, reason="insufficient cash for poach bonus")
    wc = party_cash_account(employee)
    world.ledger.ensure_account(wc)
    pay = world.ledger.transfer(debit=pc, credit=wc, amount_cents=bonus)
    if isinstance(pay, MoneyErr):
        return ActionErr(ok=False, reason=pay.reason)
    old_employer = str(target.get("employer") or "")
    target["employer"] = str(poacher)
    target["wage_per_tick_cents"] = int(new_wage_per_tick_cents)
    interval = max(1, int(target.get("wage_interval_ticks", 1)))
    target["next_wage_tick"] = int(world.tick) + interval
    log_event(
        world,
        "worker_poach",
        f"{poacher} poached worker {target.get('contract_id')} from {old_employer}"
        f" (new wage {new_wage_per_tick_cents}¢/tick, signing bonus ${bonus / 100:.2f})",
        poacher=str(poacher),
        prev_employer=old_employer,
        contract_id=str(target.get("contract_id")),
        new_wage_cents=int(new_wage_per_tick_cents),
        bonus_cents=int(bonus),
    )
    return ActionOk(ok=True)


def request_labor_transport_action(
    world: World,
    employer: PartyId,
    employee: PartyId,
    src_region: str,
    dst_region: str,
    workers: int,
) -> ActionResult:
    """Player-facing wrapper around the labor-transport scheduler."""
    from realm.population.labor import request_labor_transport

    r = request_labor_transport(
        world,
        employer=employer,
        employee=employee,
        src_region=src_region,
        dst_region=dst_region,
        workers=workers,
    )
    if r.get("ok"):
        return ActionOk(ok=True)
    return ActionErr(ok=False, reason=str(r.get("reason", "error")))

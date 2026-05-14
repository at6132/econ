"""Player / agent actions — all return {ok: bool, reason?: str}."""

from __future__ import annotations

from typing import Any, Literal, TypedDict, Union

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.plot_logistics import harvest_plot_output_to_party
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.production import start_production
from realm.world import BusinessRecord, Plot, SurveyReport, World


class ActionOk(TypedDict):
    ok: Literal[True]


class ActionErr(TypedDict):
    ok: Literal[False]
    reason: str


ActionResult = Union[ActionOk, ActionErr]

SURVEY_COST_CENTS = 50_000  # $500.00 per first-hour script

BUSINESS_REGISTRATION_FEE_CENTS = 1_000  # $10.00 — Sprint 5 — Phase A
BUSINESS_NAME_MIN_LEN = 3
BUSINESS_NAME_MAX_LEN = 40

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


def claim_plot(world: World, party: PartyId, plot_id: PlotId) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return ActionErr(ok=False, reason="unknown plot")
    if plot.owner is not None:
        return ActionErr(ok=False, reason="plot already claimed")
    # Sprint 3 — Phase B.2: claim fee scales with population density. Frontier
    # plots (density 0.0) cost nothing; dense plots near pop hubs cost up to
    # CLAIM_COST_PEAK_CENTS. The cost is sunk to system_reserve.
    from realm.world import claim_cost_cents_for_plot

    cost = int(claim_cost_cents_for_plot(world, plot_id))
    if cost > 0:
        cash = party_cash_account(party)
        world.ledger.ensure_account(cash)
        if world.ledger.balance(cash) < cost:
            return ActionErr(ok=False, reason="insufficient cash for claim fee")
        tr = world.ledger.transfer(
            debit=cash, credit=system_reserve_account(), amount_cents=cost
        )
        if isinstance(tr, MoneyErr):
            return ActionErr(ok=False, reason=tr.reason)
    plot.owner = party
    world.parties.add(party)
    from realm.world import ensure_party_recipe_book

    ensure_party_recipe_book(world, party)
    log_event(
        world,
        "claim",
        f"{party} claimed plot {plot_id}"
        + (f" (paid ${cost / 100:.2f} land fee)" if cost > 0 else ""),
        party=str(party),
        plot_id=str(plot_id),
        cost_cents=cost,
    )
    return ActionOk(ok=True)


def survey_plot(world: World, party: PartyId, plot_id: PlotId) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return ActionErr(ok=False, reason="unknown plot")
    if plot.owner != party:
        return ActionErr(ok=False, reason="not your plot")
    if plot.surveyed:
        return ActionErr(ok=False, reason="already surveyed")
    cash = party_cash_account(party)
    res = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=SURVEY_COST_CENTS,
    )
    if isinstance(res, MoneyErr):
        return ActionErr(ok=False, reason=res.reason)
    plot.surveyed = True
    create_survey_report(world, party, plot_id, is_deep=False)
    log_event(
        world,
        "survey",
        f"{party} surveyed {plot_id} (paid ${SURVEY_COST_CENTS / 100:.0f})",
        party=str(party),
        plot_id=str(plot_id),
        cost_cents=SURVEY_COST_CENTS,
    )
    return ActionOk(ok=True)


# ─────────────────── Sprint 4 — Phase A: tradeable survey reports ───────────────────


def _report_ownership_map(world: World) -> dict[str, str]:
    """``scenario_state["report_ownership"]`` accessor (auto-init)."""
    raw = world.scenario_state.setdefault("report_ownership", {})
    if not isinstance(raw, dict):
        world.scenario_state["report_ownership"] = {}
        raw = world.scenario_state["report_ownership"]
    return raw


def _standard_grades_for_plot(plot: Plot) -> dict[str, float]:
    """All standard-survey-visible grades for the plot's subsurface."""
    sub = plot.subsurface
    return {
        "iron_ore_grade": float(sub.iron_ore_grade),
        "copper_ore_grade": float(sub.copper_ore_grade),
        "clay_grade": float(sub.clay_grade),
        "coal_grade": float(sub.coal_grade),
        "sulfur_grade": float(sub.sulfur_grade),
        "saltpeter_grade": float(sub.saltpeter_grade),
        "tin_grade": float(sub.tin_grade),
        "lead_grade": float(sub.lead_grade),
        "phosphate_grade": float(sub.phosphate_grade),
        "silica_grade": float(sub.silica_grade),
    }


def _deep_grades_for_plot(plot: Plot) -> dict[str, float]:
    """Adds the Tier-3 grades on top of standard ones."""
    out = _standard_grades_for_plot(plot)
    sub = plot.subsurface
    out["platinum_grade"] = float(sub.platinum_grade)
    out["oil_shale_grade"] = float(sub.oil_shale_grade)
    out["rare_earth_grade"] = float(sub.rare_earth_grade)
    return out


def create_survey_report(
    world: World, conducted_by: PartyId, plot_id: PlotId, *, is_deep: bool
) -> SurveyReport | None:
    """Create + register a fresh SurveyReport owned by ``conducted_by``.

    Returns ``None`` if the plot is unknown (defensive — survey-action paths
    already validate). The plot's surveyed flag is the caller's concern.
    """
    plot = world.plots.get(plot_id)
    if plot is None:
        return None
    world.next_report_seq += 1
    report_id = f"sr-{world.next_report_seq}"
    grades = _deep_grades_for_plot(plot) if is_deep else _standard_grades_for_plot(plot)
    report = SurveyReport(
        report_id=report_id,
        plot_id=plot_id,
        conducted_by=conducted_by,
        conducted_at_tick=int(world.tick),
        grades=grades,
        survey_type="deep" if is_deep else "standard",
        is_deep=bool(is_deep),
    )
    world.survey_reports[report_id] = report
    _report_ownership_map(world)[report_id] = str(conducted_by)
    log_event(
        world,
        "survey_report_created",
        f"Survey report {report_id} created for {plot_id} ({report.survey_type})",
        party=str(conducted_by),
        plot_id=str(plot_id),
        report_id=report_id,
        survey_type=report.survey_type,
    )
    return report


def transfer_survey_report(
    world: World,
    from_party: PartyId,
    to_party: PartyId,
    report_id: str,
    price_cents: int,
) -> dict:
    """Sell a survey report from one party to another (Sprint 4 — Phase A).

    Deducts ``price_cents`` from ``to_party`` and credits ``from_party``.
    Updates ``report_ownership[report_id]``. Emits ``survey_report_transferred``.
    """
    if price_cents < 0:
        return {"ok": False, "reason": "price must be non-negative"}
    if from_party == to_party:
        return {"ok": False, "reason": "buyer and seller must differ"}
    report = world.survey_reports.get(str(report_id))
    if report is None:
        return {"ok": False, "reason": "unknown report"}
    owners = _report_ownership_map(world)
    current_owner = owners.get(str(report_id))
    if current_owner != str(from_party):
        return {"ok": False, "reason": "seller does not own this report"}
    if to_party not in world.parties or from_party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if price_cents > 0:
        buyer_cash = party_cash_account(to_party)
        seller_cash = party_cash_account(from_party)
        world.ledger.ensure_account(buyer_cash)
        world.ledger.ensure_account(seller_cash)
        if world.ledger.balance(buyer_cash) < price_cents:
            return {"ok": False, "reason": "insufficient cash"}
        tr = world.ledger.transfer(
            debit=buyer_cash, credit=seller_cash, amount_cents=price_cents
        )
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
    owners[str(report_id)] = str(to_party)
    log_event(
        world,
        "survey_report_transferred",
        f"{from_party} sold survey report {report_id} to {to_party} for ${price_cents / 100:.2f}",
        from_party=str(from_party),
        to_party=str(to_party),
        report_id=str(report_id),
        plot_id=str(report.plot_id),
        survey_type=report.survey_type,
        price_cents=int(price_cents),
    )
    return {
        "ok": True,
        "report_id": str(report_id),
        "new_owner": str(to_party),
        "price_cents": int(price_cents),
        "grades": dict(report.grades),
        "plot_id": str(report.plot_id),
        "survey_type": report.survey_type,
    }


def list_survey_report(
    world: World, party: PartyId, report_id: str, ask_price_cents: int
) -> dict:
    """List a survey report on the intelligence market (Sprint 4 — Phase A)."""
    if ask_price_cents <= 0:
        return {"ok": False, "reason": "ask price must be positive"}
    report = world.survey_reports.get(str(report_id))
    if report is None:
        return {"ok": False, "reason": "unknown report"}
    owners = _report_ownership_map(world)
    if owners.get(str(report_id)) != str(party):
        return {"ok": False, "reason": "you do not own this report"}
    for row in world.intel_listings:
        if (
            str(row.get("report_id", "")) == str(report_id)
            and str(row.get("status", "")) == "active"
        ):
            return {"ok": False, "reason": "report already listed"}
    world.next_intel_listing_seq += 1
    listing_id = f"int-{world.next_intel_listing_seq}"
    world.intel_listings.append(
        {
            "listing_id": listing_id,
            "seller": str(party),
            "report_id": str(report_id),
            "ask_price_cents": int(ask_price_cents),
            "listed_at_tick": int(world.tick),
            "status": "active",
        }
    )
    log_event(
        world,
        "intel_listing_created",
        f"{party} listed survey report {report_id} for ${ask_price_cents / 100:.2f} "
        f"(plot {report.plot_id}, {report.survey_type})",
        party=str(party),
        listing_id=listing_id,
        report_id=str(report_id),
        plot_id=str(report.plot_id),
        ask_price_cents=int(ask_price_cents),
        survey_type=report.survey_type,
    )
    return {
        "ok": True,
        "listing_id": listing_id,
        "report_id": str(report_id),
        "ask_price_cents": int(ask_price_cents),
    }


def cancel_survey_report_listing(world: World, party: PartyId, listing_id: str) -> dict:
    """Cancel an active intel listing (seller only)."""
    for row in world.intel_listings:
        if str(row.get("listing_id", "")) != str(listing_id):
            continue
        if str(row.get("seller", "")) != str(party):
            return {"ok": False, "reason": "not your listing"}
        if str(row.get("status", "")) != "active":
            return {"ok": False, "reason": "listing not active"}
        row["status"] = "cancelled"
        log_event(
            world,
            "intel_listing_cancelled",
            f"{party} cancelled intel listing {listing_id}",
            party=str(party),
            listing_id=str(listing_id),
        )
        return {"ok": True}
    return {"ok": False, "reason": "unknown listing"}


def buy_survey_report(world: World, buyer: PartyId, listing_id: str) -> dict:
    """Atomically purchase a listed survey report (Sprint 4 — Phase A)."""
    target: dict | None = None
    for row in world.intel_listings:
        if str(row.get("listing_id", "")) == str(listing_id):
            target = row
            break
    if target is None:
        return {"ok": False, "reason": "unknown listing"}
    if str(target.get("status", "")) != "active":
        return {"ok": False, "reason": "listing not active"}
    seller = PartyId(str(target.get("seller", "")))
    report_id = str(target.get("report_id", ""))
    price = int(target.get("ask_price_cents", 0))
    if buyer == seller:
        return {"ok": False, "reason": "cannot buy your own listing"}
    tr = transfer_survey_report(world, seller, buyer, report_id, price)
    if not tr.get("ok"):
        return dict(tr)
    target["status"] = "sold"
    target["buyer"] = str(buyer)
    target["sold_at_tick"] = int(world.tick)
    log_event(
        world,
        "intel_listing_sold",
        f"{buyer} bought intel listing {listing_id} ({report_id}) for ${price / 100:.2f}",
        buyer=str(buyer),
        seller=str(seller),
        listing_id=str(listing_id),
        report_id=report_id,
        price_cents=price,
    )
    return {
        "ok": True,
        "listing_id": str(listing_id),
        "report_id": report_id,
        "price_cents": price,
        "grades": tr.get("grades", {}),
        "plot_id": tr.get("plot_id", ""),
        "survey_type": tr.get("survey_type", ""),
    }


# ─────────────────── Sprint 5 — Phase A: business registration ───────────────────


_BUSINESS_NAME_ALLOWED_PUNCT = frozenset(" '.&-,")


def _is_valid_business_name(name: str) -> bool:
    """3–40 chars, alphanumeric + spaces + apostrophes only.

    No leading/trailing whitespace; collapsed-but-not-empty internal chars.
    """
    if not isinstance(name, str):
        return False
    stripped = name.strip()
    if stripped != name:
        return False
    if not (BUSINESS_NAME_MIN_LEN <= len(name) <= BUSINESS_NAME_MAX_LEN):
        return False
    for ch in name:
        if ch.isalnum() or ch in _BUSINESS_NAME_ALLOWED_PUNCT:
            continue
        return False
    return True


def _business_name_taken(world: World, name: str) -> bool:
    target = name.casefold().strip()
    for rec in world.business_registry.values():
        if rec.business_name.casefold().strip() == target:
            return True
    return False


def register_business(
    world: World, party: PartyId, name: str, description: str = ""
) -> dict:
    """Register ``party``'s business identity (Sprint 5 — Phase A).

    Charges ``BUSINESS_REGISTRATION_FEE_CENTS`` to the system reserve and
    promotes ``name`` to the authoritative display label via
    ``world.party_display_names``. Idempotent only against the same party
    re-registering the same name; collisions across parties are rejected.
    """
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if not _is_valid_business_name(name):
        return {
            "ok": False,
            "reason": (
                f"name must be {BUSINESS_NAME_MIN_LEN}\u2013{BUSINESS_NAME_MAX_LEN} "
                "characters and contain only letters, digits, spaces, or apostrophes"
            ),
        }
    if not isinstance(description, str) or len(description) > 240:
        return {"ok": False, "reason": "description must be a string \u2264 240 characters"}
    existing = world.business_registry.get(str(party))
    if existing is not None and existing.business_name == name:
        return {
            "ok": True,
            "party_id": str(party),
            "business_name": existing.business_name,
            "description": existing.description,
            "registered_at_tick": int(existing.registered_at_tick),
            "already_registered": True,
        }
    if _business_name_taken(world, name):
        return {"ok": False, "reason": "business name already taken"}
    cash = party_cash_account(party)
    world.ledger.ensure_account(cash)
    if world.ledger.balance(cash) < BUSINESS_REGISTRATION_FEE_CENTS:
        return {"ok": False, "reason": "insufficient cash for registration fee"}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=BUSINESS_REGISTRATION_FEE_CENTS,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    record = BusinessRecord(
        party_id=party,
        business_name=name,
        description=description,
        registered_at_tick=int(world.tick),
    )
    world.business_registry[str(party)] = record
    world.party_display_names[str(party)] = name
    log_event(
        world,
        "business_registered",
        f"A new enterprise registered on the frontier: '{name}'.",
        party=str(party),
        business_name=name,
        fee_cents=BUSINESS_REGISTRATION_FEE_CENTS,
    )
    world.world_feed_log.append(
        {
            "tick": int(world.tick),
            "kind": "world_feed",
            "feed_source": "business_registered",
            "message": f"A new enterprise registered on the frontier: '{name}'.",
            "party": str(party),
            "business_name": name,
        }
    )
    return {
        "ok": True,
        "party_id": str(party),
        "business_name": name,
        "description": description,
        "registered_at_tick": int(world.tick),
        "fee_cents": BUSINESS_REGISTRATION_FEE_CENTS,
    }


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

    Sprint 3 — Phase C.2: the bonus is multiplied by the regional labor-scarcity
    factor (1.0 / 1.25 / 1.6) and the action is rejected if the employer's
    region pool can't supply ``workers_count`` (or in critical bands, the batch
    exceeds the per-action share cap).
    """
    if signing_bonus_cents <= 0:
        return ActionErr(ok=False, reason="signing bonus must be positive")
    if wage_per_tick_cents < 0:
        return ActionErr(ok=False, reason="wage_per_tick_cents must be non-negative")
    if wage_interval_ticks < 1:
        return ActionErr(ok=False, reason="wage_interval_ticks must be at least 1")
    if workers_count < 1:
        return ActionErr(ok=False, reason="workers_count must be at least 1")
    if employee not in HIRABLE_NPCS:
        return ActionErr(ok=False, reason="that party is not on the hire list (stub)")
    if employer not in world.parties or employee not in world.parties:
        return ActionErr(ok=False, reason="unknown party")
    # Regional labor cost premium + pool draw (Sprint 3 — Phase C.2).
    # Skipped for Frontier and minimal testbeds where the labor market is
    # inactive (``labor_market_active`` returns False there).
    from realm.labor import (
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
            from realm.labor import increment_pool as _restore_pool

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


def harvest_plot_output_stock(
    world: World, party: PartyId, plot_id: PlotId, material: str, qty: int
) -> ActionResult:
    r = harvest_plot_output_to_party(world, party, plot_id, MaterialId(material), qty)
    if r.get("ok"):
        return ActionOk(ok=True)
    return ActionErr(ok=False, reason=str(r.get("reason", "error")))


def plot_by_id(world: World, plot_id: PlotId) -> Plot | None:
    return world.plots.get(plot_id)


def start_production_on_plot(
    world: World, party: PartyId, plot_id: PlotId, recipe_id: str
) -> dict[str, Any]:
    """Proxy to ``production.start_production`` (full result dict for API / agents)."""
    return start_production(world, party, plot_id, recipe_id)


def register_route(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    from_region: str,
    to_region: str,
    fee_per_tile_cents: int,
) -> dict[str, Any]:
    """Register ``party`` as the operator of a region-to-region shipping route.

    Proxy to :func:`realm.route_operators.register_route`. See that function's
    docstring for the full precondition list.
    """
    from realm.route_operators import register_route as _register

    return _register(world, party, plot_id, from_region, to_region, fee_per_tile_cents)


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
    # Signing bonus = the wage premium per tick (cheap but visible).
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
    # Reset wage scheduling under the new employer.
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
    from realm.labor import request_labor_transport

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


def revise_route_fee(
    world: World,
    party: PartyId,
    route_key: str,
    new_fee_per_tile_cents: int,
) -> dict[str, Any]:
    """Update the per-tile fee on a route the ``party`` already operates."""
    from realm.route_operators import set_operator_fee

    return set_operator_fee(world, party, route_key, new_fee_per_tile_cents)

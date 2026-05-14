"""Plot-level actions: claim, survey, and the survey-report market.

Functions:
  * ``claim_plot``                   — claim ownership of a plot (paid)
  * ``survey_plot``                  — standard survey (paid; reveals Tier-1/2 grades)
  * ``create_survey_report``         — internal helper used by ``survey_plot``
                                       and the deep-survey path
  * ``transfer_survey_report``       — sell a report from one party to another
  * ``list_survey_report``           — list a report on the intel market
  * ``cancel_survey_report_listing`` — pull an active intel listing
  * ``buy_survey_report``            — atomically purchase a listed report
  * ``plot_by_id``                   — small lookup helper
"""

from __future__ import annotations

from realm.actions._shared import ActionErr, ActionOk, ActionResult
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.world import Plot, SurveyReport, World

SURVEY_COST_CENTS = 50_000  # $500.00 per first-hour script


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


def plot_by_id(world: World, plot_id: PlotId) -> Plot | None:
    return world.plots.get(plot_id)

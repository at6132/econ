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

# Phase 9B — plot trading. The transfer fee is a small registry fee paid by
# the seller to ``system:reserve`` (a "land office" cost — keeps the channel
# clean for v1; can be redirected to a town treasury later). Set to 1 % of
# sale price with a floor + cap so cheap frontier flips stay affordable.
PLOT_TRANSFER_FEE_BPS: int = 100  # 1 %
PLOT_TRANSFER_FEE_MIN_CENTS: int = 1_000  # $10 floor
PLOT_TRANSFER_FEE_MAX_CENTS: int = 100_000  # $1,000 cap

# Phase 9B — speculative surveying authorization window. Owners grant a
# surveyor permission to survey their plot for ``SURVEY_AUTH_DURATION_TICKS``
# game-minutes (default 30 game-days). The surveyor then runs ``survey_plot_for``
# at their own cost and keeps the report.
SURVEY_AUTH_DURATION_TICKS: int = 30 * 1_440  # 30 game-days


def _plot_transfer_fee_cents(price_cents: int) -> int:
    """Compute the registry fee on a plot sale (clamped to floor/cap)."""
    if price_cents <= 0:
        return 0
    raw = price_cents * PLOT_TRANSFER_FEE_BPS // 10_000
    if raw < PLOT_TRANSFER_FEE_MIN_CENTS:
        return PLOT_TRANSFER_FEE_MIN_CENTS
    if raw > PLOT_TRANSFER_FEE_MAX_CENTS:
        return PLOT_TRANSFER_FEE_MAX_CENTS
    return int(raw)


def claim_plot(world: World, party: PartyId, plot_id: PlotId) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return ActionErr(ok=False, reason="unknown plot")
    if plot.owner is not None:
        return ActionErr(ok=False, reason="plot already claimed")
    from realm.production.recipe_sites import plot_allows_structure

    if not plot_allows_structure(plot):
        return ActionErr(ok=False, reason="cannot claim water plots")
    # Sprint 3 — Phase B.2: claim fee scales with population density. Frontier
    # plots (density 0.0) cost nothing; dense plots near pop hubs cost up to
    # CLAIM_COST_PEAK_CENTS. The cost is sunk to system_reserve.
    from realm.world import claim_cost_cents_for_plot

    cost = int(claim_cost_cents_for_plot(world, plot_id))
    # Phase 9I - progressive ownership tax. Every plot the party already
    # owns multiplies the next claim fee by +20%, capped at 5x. This
    # makes large land-grabs strategically expensive (anti-monopoly)
    # without blocking honest expansion. Frontier plots (density 0) are
    # still free at any quantity; we only mark up the densest-zone fee.
    owned_count = sum(
        1 for p in world.plots.values() if p.owner == party
    )
    if cost > 0 and owned_count > 0:
        multiplier_bps = min(10_000 + owned_count * 2_000, 50_000)
        cost = cost * multiplier_bps // 10_000
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


# ─────────────────── Phase 9B — plot trading ───────────────────


def _active_plot_listing_for(world: World, plot_id: PlotId) -> dict | None:
    for row in world.plot_listings:
        if (
            str(row.get("plot_id", "")) == str(plot_id)
            and str(row.get("status", "")) == "active"
        ):
            return row
    return None


def transfer_plot(
    world: World,
    from_party: PartyId,
    to_party: PartyId,
    plot_id: PlotId,
    price_cents: int,
) -> dict:
    """Atomically transfer plot ownership from ``from_party`` to ``to_party``.

    Cash flow: ``to_party`` pays ``price_cents`` to ``from_party``; the seller
    additionally pays a registry fee (``_plot_transfer_fee_cents``) to
    ``system:reserve``. Ownership flips and any associated buildings stay on
    the plot (their owner-of-record on the building row is unchanged — those
    are a separate primitive). Active sale listings for the plot are marked
    cancelled.
    """
    if price_cents < 0:
        return {"ok": False, "reason": "price must be non-negative"}
    if from_party == to_party:
        return {"ok": False, "reason": "buyer and seller must differ"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != from_party:
        return {"ok": False, "reason": "seller does not own this plot"}
    if to_party not in world.parties or from_party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    buyer_cash = party_cash_account(to_party)
    seller_cash = party_cash_account(from_party)
    world.ledger.ensure_account(buyer_cash)
    world.ledger.ensure_account(seller_cash)
    fee = _plot_transfer_fee_cents(price_cents)
    if price_cents > 0:
        if world.ledger.balance(buyer_cash) < price_cents:
            return {"ok": False, "reason": "insufficient cash"}
        tr_pay = world.ledger.transfer(
            debit=buyer_cash, credit=seller_cash, amount_cents=price_cents
        )
        if isinstance(tr_pay, MoneyErr):
            return {"ok": False, "reason": tr_pay.reason}
    if fee > 0:
        if world.ledger.balance(seller_cash) < fee:
            if price_cents > 0:
                world.ledger.transfer(
                    debit=seller_cash, credit=buyer_cash, amount_cents=price_cents
                )
            return {"ok": False, "reason": "seller cannot pay registry fee"}
        tr_fee = world.ledger.transfer(
            debit=seller_cash,
            credit=system_reserve_account(),
            amount_cents=fee,
        )
        if isinstance(tr_fee, MoneyErr):
            if price_cents > 0:
                world.ledger.transfer(
                    debit=seller_cash, credit=buyer_cash, amount_cents=price_cents
                )
            return {"ok": False, "reason": tr_fee.reason}
    plot.owner = to_party
    listing = _active_plot_listing_for(world, plot_id)
    if listing is not None and str(listing.get("seller", "")) == str(from_party):
        listing["status"] = "sold"
        listing["buyer"] = str(to_party)
        listing["sold_at_tick"] = int(world.tick)
    log_event(
        world,
        "plot_transfer",
        f"{from_party} sold plot {plot_id} to {to_party} for ${price_cents / 100:.2f} "
        f"(registry fee ${fee / 100:.2f})",
        from_party=str(from_party),
        to_party=str(to_party),
        plot_id=str(plot_id),
        price_cents=int(price_cents),
        fee_cents=int(fee),
    )
    return {
        "ok": True,
        "plot_id": str(plot_id),
        "new_owner": str(to_party),
        "price_cents": int(price_cents),
        "fee_cents": int(fee),
    }


def list_plot_for_sale(
    world: World, party: PartyId, plot_id: PlotId, ask_price_cents: int
) -> dict:
    """Open an active sale listing for one of the party's plots."""
    if ask_price_cents <= 0:
        return {"ok": False, "reason": "ask price must be positive"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "you do not own this plot"}
    if _active_plot_listing_for(world, plot_id) is not None:
        return {"ok": False, "reason": "plot already listed"}
    world.next_plot_listing_seq += 1
    listing_id = f"plot-{world.next_plot_listing_seq}"
    world.plot_listings.append(
        {
            "listing_id": listing_id,
            "seller": str(party),
            "plot_id": str(plot_id),
            "ask_price_cents": int(ask_price_cents),
            "listed_at_tick": int(world.tick),
            "status": "active",
        }
    )
    log_event(
        world,
        "plot_listing_created",
        f"{party} listed plot {plot_id} for ${ask_price_cents / 100:.2f}",
        party=str(party),
        listing_id=listing_id,
        plot_id=str(plot_id),
        ask_price_cents=int(ask_price_cents),
    )
    return {
        "ok": True,
        "listing_id": listing_id,
        "plot_id": str(plot_id),
        "ask_price_cents": int(ask_price_cents),
    }


def cancel_plot_listing(world: World, party: PartyId, listing_id: str) -> dict:
    """Cancel an active plot listing (seller only)."""
    for row in world.plot_listings:
        if str(row.get("listing_id", "")) != str(listing_id):
            continue
        if str(row.get("seller", "")) != str(party):
            return {"ok": False, "reason": "not your listing"}
        if str(row.get("status", "")) != "active":
            return {"ok": False, "reason": "listing not active"}
        row["status"] = "cancelled"
        log_event(
            world,
            "plot_listing_cancelled",
            f"{party} cancelled plot listing {listing_id}",
            party=str(party),
            listing_id=str(listing_id),
            plot_id=str(row.get("plot_id", "")),
        )
        return {"ok": True}
    return {"ok": False, "reason": "unknown listing"}


def buy_plot_listing(world: World, buyer: PartyId, listing_id: str) -> dict:
    """Atomically purchase a listed plot at its ask price."""
    target: dict | None = None
    for row in world.plot_listings:
        if str(row.get("listing_id", "")) == str(listing_id):
            target = row
            break
    if target is None:
        return {"ok": False, "reason": "unknown listing"}
    if str(target.get("status", "")) != "active":
        return {"ok": False, "reason": "listing not active"}
    seller = PartyId(str(target.get("seller", "")))
    plot_id = PlotId(str(target.get("plot_id", "")))
    price = int(target.get("ask_price_cents", 0))
    if buyer == seller:
        return {"ok": False, "reason": "cannot buy your own listing"}
    tr = transfer_plot(world, seller, buyer, plot_id, price)
    if not tr.get("ok"):
        return dict(tr)
    log_event(
        world,
        "plot_listing_sold",
        f"{buyer} bought plot listing {listing_id} ({plot_id}) for ${price / 100:.2f}",
        buyer=str(buyer),
        seller=str(seller),
        listing_id=str(listing_id),
        plot_id=str(plot_id),
        price_cents=price,
    )
    return {
        "ok": True,
        "listing_id": str(listing_id),
        "plot_id": str(plot_id),
        "new_owner": str(buyer),
        "price_cents": price,
        "fee_cents": int(tr.get("fee_cents", 0)),
    }


def subdivide_plot(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    partitions: list[dict[str, int | str]],
) -> ActionResult:
    from realm.world.plot_scale import CELL_SIDE_METRES, cells_occupied, plot_grid_side

    plot = world.plots.get(plot_id)
    if plot is None or plot.owner != party:
        return ActionErr(ok=False, reason="not your plot")
    grid_w, grid_h = plot_grid_side(plot)
    if any(sp.parent_plot_id == str(plot_id) for sp in world.sub_plots.values()):
        return ActionErr(ok=False, reason="plot is already subdivided")
    if len(partitions) < 2:
        return ActionErr(ok=False, reason="need at least 2 partitions to subdivide")
    if len(partitions) > 9:
        return ActionErr(ok=False, reason="maximum 9 sub-plots per plot")

    all_cells: set[tuple[int, int]] = set()
    for p in partitions:
        gx = int(p["grid_x"])
        gy = int(p["grid_y"])
        gw = int(p["grid_w"])
        gh = int(p["grid_h"])
        if gw < 2 or gh < 2:
            return ActionErr(
                ok=False, reason="minimum sub-plot size is 2×2 cells (20m×20m)"
            )
        cells = cells_occupied(gx, gy, gw, gh)
        overlap = all_cells & cells
        if overlap:
            return ActionErr(ok=False, reason=f"partition overlaps at cells {overlap}")
        if gx < 0 or gy < 0 or gx + gw > grid_w or gy + gh > grid_h:
            return ActionErr(ok=False, reason="partition exceeds plot bounds")
        all_cells |= cells

    full_plot_cells = cells_occupied(0, 0, grid_w, grid_h)
    if all_cells != full_plot_cells:
        return ActionErr(
            ok=False,
            reason="partitions must cover the entire build grid for this parcel",
        )

    fee = len(partitions) * 10_000
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < fee:
        return ActionErr(ok=False, reason=f"need ${fee / 100:.2f} surveyor fee")
    tr = world.ledger.transfer(
        debit=cash, credit=system_reserve_account(), amount_cents=fee
    )
    if isinstance(tr, MoneyErr):
        return ActionErr(ok=False, reason=tr.reason)

    created: list[str] = []
    labels = "ABCDEFGHI"
    for i, p in enumerate(partitions):
        sp_id = f"{plot_id}:{labels[i]}"
        gw = int(p["grid_w"])
        gh = int(p["grid_h"])
        area = gw * gh * (CELL_SIDE_METRES**2)
        from realm.world.world import SubPlot

        sp = SubPlot(
            sub_plot_id=sp_id,
            parent_plot_id=str(plot_id),
            owner=str(party),
            grid_x=int(p["grid_x"]),
            grid_y=int(p["grid_y"]),
            grid_w=gw,
            grid_h=gh,
            area_sq_metres=area,
            listed_for_sale=False,
            ask_price_cents=0,
            lease_rights=None,
        )
        world.sub_plots[sp_id] = sp
        created.append(sp_id)

    log_event(
        world,
        "plot_subdivided",
        f"{party} subdivided plot {plot_id} into {len(partitions)} sub-plots",
        party=str(party),
        plot_id=str(plot_id),
        sub_plot_ids=created,
    )
    return ActionOk(ok=True, sub_plot_ids=created, surveyor_fee_cents=fee)


def list_sub_plot_for_sale(
    world: World, party: PartyId, sub_plot_id: str, ask_price_cents: int
) -> ActionResult:
    sp = world.sub_plots.get(sub_plot_id)
    if sp is None or sp.owner != str(party):
        return ActionErr(ok=False, reason="not your sub-plot")
    if ask_price_cents <= 0:
        return ActionErr(ok=False, reason="ask price must be positive")
    sp.listed_for_sale = True
    sp.ask_price_cents = int(ask_price_cents)
    return ActionOk(ok=True, sub_plot_id=sub_plot_id, ask_price_cents=ask_price_cents)


def buy_sub_plot(
    world: World, buyer: PartyId, sub_plot_id: str
) -> ActionResult:
    sp = world.sub_plots.get(sub_plot_id)
    if sp is None or not sp.listed_for_sale:
        return ActionErr(ok=False, reason="sub-plot not listed for sale")
    seller = PartyId(str(sp.owner))
    ask = int(sp.ask_price_cents)
    bc = party_cash_account(buyer)
    sc = party_cash_account(seller)
    if world.ledger.balance(bc) < ask:
        return ActionErr(ok=False, reason=f"need ${ask / 100:.2f} to buy this sub-plot")
    tr = world.ledger.transfer(debit=bc, credit=sc, amount_cents=ask)
    if isinstance(tr, MoneyErr):
        return ActionErr(ok=False, reason=tr.reason)
    sp.owner = str(buyer)
    sp.listed_for_sale = False
    sp.ask_price_cents = 0
    return ActionOk(ok=True, price_paid_cents=ask)


# ─────────────────── Phase 9B — speculative surveying ───────────────────


def authorize_survey(
    world: World, owner: PartyId, surveyor: PartyId, plot_id: PlotId
) -> dict:
    """Grant a surveyor a time-limited right to survey one of your plots.

    Authorizations are one-shot: the row is removed when consumed by
    ``survey_plot_for`` or when the expiry tick is reached.
    """
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != owner:
        return {"ok": False, "reason": "you do not own this plot"}
    if owner == surveyor:
        return {"ok": False, "reason": "self-authorization not needed"}
    if surveyor not in world.parties:
        return {"ok": False, "reason": "unknown surveyor"}
    expires = int(world.tick) + SURVEY_AUTH_DURATION_TICKS
    world.survey_authorizations.append(
        {
            "plot_id": str(plot_id),
            "surveyor": str(surveyor),
            "owner": str(owner),
            "granted_at_tick": int(world.tick),
            "expires_at_tick": expires,
        }
    )
    log_event(
        world,
        "survey_authorized",
        f"{owner} authorized {surveyor} to survey {plot_id} (expires tick {expires})",
        owner=str(owner),
        surveyor=str(surveyor),
        plot_id=str(plot_id),
        expires_at_tick=expires,
    )
    return {"ok": True, "plot_id": str(plot_id), "expires_at_tick": expires}


def _consume_survey_auth(
    world: World, surveyor: PartyId, plot_id: PlotId
) -> bool:
    """Find + drop one active authorization for (surveyor, plot)."""
    for i, row in enumerate(world.survey_authorizations):
        if str(row.get("plot_id")) != str(plot_id):
            continue
        if str(row.get("surveyor")) != str(surveyor):
            continue
        if int(row.get("expires_at_tick", 0)) < int(world.tick):
            continue
        world.survey_authorizations.pop(i)
        return True
    return False


def survey_plot_for(world: World, surveyor: PartyId, plot_id: PlotId) -> dict:
    """Speculative / on-contract survey of a plot the surveyor does **not** own.

    Allowed when:
      * the plot has no owner (frontier — anyone may speculatively survey), or
      * an active ``survey_authorizations`` row exists for this surveyor
        + plot pair (consumed on success).

    The survey cost is paid by the surveyor; the resulting SurveyReport is
    owned by the surveyor (they can then sell it to the plot owner or anyone
    else via the existing intel-listing market).
    """
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.surveyed:
        return {"ok": False, "reason": "already surveyed"}
    if plot.owner == surveyor:
        return {"ok": False, "reason": "use survey_plot for your own plot"}
    if plot.owner is not None and not _consume_survey_auth(world, surveyor, plot_id):
        return {
            "ok": False,
            "reason": "speculative survey requires the owner's authorization",
        }
    cash = party_cash_account(surveyor)
    world.ledger.ensure_account(cash)
    res = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=SURVEY_COST_CENTS,
    )
    if isinstance(res, MoneyErr):
        return {"ok": False, "reason": res.reason}
    plot.surveyed = True
    create_survey_report(world, surveyor, plot_id, is_deep=False)
    log_event(
        world,
        "survey",
        f"{surveyor} surveyed {plot_id} on commission (paid ${SURVEY_COST_CENTS / 100:.0f})",
        party=str(surveyor),
        plot_id=str(plot_id),
        cost_cents=SURVEY_COST_CENTS,
        speculative=True,
    )
    return {"ok": True, "plot_id": str(plot_id)}

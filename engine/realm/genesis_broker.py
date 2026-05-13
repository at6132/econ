"""Survey-data broker NPC (Sprint 4 — Phase A.4).

A single Tier-2 agent per Genesis world that creates a real two-sided market
for survey intelligence even before players are doing brokering themselves:

- Pays settlers ``BROKER_BUY_STANDARD_CENTS`` (200¢ = $2.00 a report) for any
  standard report whose subsurface contains at least one grade ≥ 0.5. Deep
  reports get a higher offer.
- Relists every report it picks up at ``BROKER_RESELL_STANDARD_CENTS`` (600¢)
  or ``BROKER_RESELL_DEEP_CENTS`` (1500¢) on the intelligence market.
- Runs once per game-day on the same cadence as other Tier-2 agents.

The broker never publishes which plots it has data on — players see only the
report's plot_id, survey type, and price (that's what they're paying to see
the grades for).
"""

from __future__ import annotations

from typing import Final

from realm.actions import (
    cancel_survey_report_listing,
    list_survey_report,
    transfer_survey_report,
)
from realm.event_log import log_event
from realm.ids import PartyId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import SurveyReport, World


__all__ = [
    "SURVEY_BROKER_PARTY_ID",
    "SURVEY_BROKER_DISPLAY_NAME",
    "BROKER_BUY_STANDARD_CENTS",
    "BROKER_BUY_DEEP_CENTS",
    "BROKER_RESELL_STANDARD_CENTS",
    "BROKER_RESELL_DEEP_CENTS",
    "BROKER_HIGH_GRADE_THRESHOLD",
    "seed_survey_broker",
    "tick_survey_broker",
]


SURVEY_BROKER_PARTY_ID: Final[PartyId] = PartyId("survey_broker_central")
SURVEY_BROKER_DISPLAY_NAME: Final[str] = "Central Survey Brokerage"
SURVEY_BROKER_STARTING_CASH_CENTS: Final[int] = 5_000_000  # $50,000 working capital

# Buy / resell parameters per the sprint spec.
BROKER_BUY_STANDARD_CENTS: Final[int] = 200
BROKER_BUY_DEEP_CENTS: Final[int] = 500
BROKER_RESELL_STANDARD_CENTS: Final[int] = 600
BROKER_RESELL_DEEP_CENTS: Final[int] = 1500
BROKER_HIGH_GRADE_THRESHOLD: Final[float] = 0.5

_TICKS_PER_GAME_DAY: Final[int] = 1440


def seed_survey_broker(
    world: World, *, starting_cash_cents: int | None = None
) -> bool:
    """Spawn the broker into a Genesis world. Idempotent. Returns True on creation."""
    if world.scenario_id != "genesis":
        return False
    pid = SURVEY_BROKER_PARTY_ID
    if pid in world.parties:
        return False
    cash = (
        starting_cash_cents
        if starting_cash_cents is not None
        else SURVEY_BROKER_STARTING_CASH_CENTS
    )
    world.parties.add(pid)
    world.reputation[str(pid)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(pid)] = SURVEY_BROKER_DISPLAY_NAME
    acct = party_cash_account(pid)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=cash,
    )
    if isinstance(tr, MoneyErr):
        return False
    log_event(
        world,
        "survey_broker_seeded",
        f"{SURVEY_BROKER_DISPLAY_NAME} opened with ${cash // 100:,} working capital",
        party=str(pid),
        starting_cash_cents=int(cash),
    )
    return True


def _is_high_grade(report: SurveyReport) -> bool:
    """At least one grade in the report is at or above the broker's threshold."""
    for grade in report.grades.values():
        try:
            if float(grade) >= BROKER_HIGH_GRADE_THRESHOLD:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _seller_listed_already(world: World, report_id: str) -> bool:
    """True if any active listing already exists for ``report_id``."""
    for row in world.intel_listings:
        if (
            str(row.get("report_id", "")) == str(report_id)
            and str(row.get("status", "")) == "active"
        ):
            return True
    return False


def tick_survey_broker(world: World) -> None:
    """Once-per-game-day broker pass (Sprint 4 — Phase A.4).

    1. Walk every settler-conducted, high-grade report not currently listed and
       offer the standard / deep buy price. Settlers always accept (it is free
       cash for them — the report stays revealed on their plot for their own
       use, and the broker resells the *document*).
    2. Relist every broker-held report at the configured resale price.
    """
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    if SURVEY_BROKER_PARTY_ID not in world.parties:
        return
    ownership = world.scenario_state.get("report_ownership") or {}
    if not isinstance(ownership, dict):
        return
    broker = SURVEY_BROKER_PARTY_ID
    broker_cash_acct = party_cash_account(broker)
    # Step 1 — buy from settlers.
    for report_id in list(ownership.keys()):
        owner = str(ownership.get(report_id, ""))
        if not owner.startswith("settler_"):
            continue
        report = world.survey_reports.get(str(report_id))
        if report is None:
            continue
        if not _is_high_grade(report):
            continue
        if _seller_listed_already(world, report_id):
            continue
        price = BROKER_BUY_DEEP_CENTS if report.is_deep else BROKER_BUY_STANDARD_CENTS
        if world.ledger.balance(broker_cash_acct) < price:
            break
        tr = transfer_survey_report(
            world,
            from_party=PartyId(owner),
            to_party=broker,
            report_id=str(report_id),
            price_cents=price,
        )
        if not tr.get("ok"):
            continue
        log_event(
            world,
            "survey_broker_bought",
            f"{SURVEY_BROKER_DISPLAY_NAME} bought {report_id} from {owner} for ${price / 100:.2f}",
            party=str(broker),
            from_party=owner,
            report_id=str(report_id),
            price_cents=price,
        )
    # Step 2 — relist broker-held reports.
    for report_id, owner in list(ownership.items()):
        if str(owner) != str(broker):
            continue
        if _seller_listed_already(world, report_id):
            continue
        report = world.survey_reports.get(str(report_id))
        if report is None:
            continue
        resell = (
            BROKER_RESELL_DEEP_CENTS if report.is_deep else BROKER_RESELL_STANDARD_CENTS
        )
        r = list_survey_report(world, broker, str(report_id), resell)
        if not r.get("ok"):
            continue
        log_event(
            world,
            "survey_broker_listed",
            f"{SURVEY_BROKER_DISPLAY_NAME} listed {report_id} for ${resell / 100:.2f}",
            party=str(broker),
            report_id=str(report_id),
            ask_price_cents=resell,
        )
    # Step 3 — opportunistically prune stale (>30 day) own listings; no-op
    # for tests but keeps the active book from growing without bound.
    cutoff = int(world.tick) - 30 * _TICKS_PER_GAME_DAY
    for row in world.intel_listings:
        if str(row.get("seller", "")) != str(broker):
            continue
        if str(row.get("status", "")) != "active":
            continue
        if int(row.get("listed_at_tick", 0)) >= cutoff:
            continue
        cancel_survey_report_listing(world, broker, str(row.get("listing_id", "")))

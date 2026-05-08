"""Player / agent actions — all return {ok: bool, reason?: str}."""

from __future__ import annotations

from typing import Literal, TypedDict, Union

from realm.event_log import log_event
from realm.ids import PartyId, PlotId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.production import start_production
from realm.world import Plot, World


class ActionOk(TypedDict):
    ok: Literal[True]


class ActionErr(TypedDict):
    ok: Literal[False]
    reason: str


ActionResult = Union[ActionOk, ActionErr]

SURVEY_COST_CENTS = 50_000  # $500.00 per first-hour script

HIRABLE_NPCS: frozenset[PartyId] = frozenset(
    {
        PartyId("t1_lumber_buyer"),
        PartyId("t1_timber_merchant"),
        PartyId("npc_grain_vendor"),
    }
)


def claim_plot(world: World, party: PartyId, plot_id: PlotId) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return ActionErr(ok=False, reason="unknown plot")
    if plot.owner is not None:
        return ActionErr(ok=False, reason="plot already claimed")
    plot.owner = party
    world.parties.add(party)
    log_event(world, "claim", f"{party} claimed plot {plot_id}", party=str(party), plot_id=str(plot_id))
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
    log_event(
        world,
        "survey",
        f"{party} surveyed {plot_id} (paid ${SURVEY_COST_CENTS / 100:.0f})",
        party=str(party),
        plot_id=str(plot_id),
        cost_cents=SURVEY_COST_CENTS,
    )
    return ActionOk(ok=True)


def hire_worker_stub(
    world: World, employer: PartyId, employee: PartyId, signing_bonus_cents: int
) -> ActionResult:
    """
    One-shot signing bonus to an NPC party (Phase 1 stub — no labor output yet).

    Employment / contracts v2 will replace this shape.
    """
    if signing_bonus_cents <= 0:
        return ActionErr(ok=False, reason="signing bonus must be positive")
    if employee not in HIRABLE_NPCS:
        return ActionErr(ok=False, reason="that party is not on the hire list (stub)")
    if employer not in world.parties or employee not in world.parties:
        return ActionErr(ok=False, reason="unknown party")
    ec = party_cash_account(employer)
    wc = party_cash_account(employee)
    if world.ledger.balance(ec) < signing_bonus_cents:
        return ActionErr(ok=False, reason="insufficient cash")
    pay = world.ledger.transfer(
        debit=ec,
        credit=wc,
        amount_cents=signing_bonus_cents,
    )
    if isinstance(pay, MoneyErr):
        return ActionErr(ok=False, reason=pay.reason)
    world.stub_hires.append(
        {
            "employer": str(employer),
            "employee": str(employee),
            "signing_bonus_cents": signing_bonus_cents,
            "tick": world.tick,
        }
    )
    log_event(
        world,
        "hire",
        f"{employer} paid {employee} ${signing_bonus_cents / 100:.2f} signing bonus (stub hire)",
        employer=str(employer),
        employee=str(employee),
        signing_bonus_cents=signing_bonus_cents,
    )
    return ActionOk(ok=True)


def plot_by_id(world: World, plot_id: PlotId) -> Plot | None:
    return world.plots.get(plot_id)


def start_production_on_plot(
    world: World, party: PartyId, plot_id: PlotId, recipe_id: str
) -> ActionResult:
    r = start_production(world, party, plot_id, recipe_id)
    if r.get("ok"):
        return ActionOk(ok=True)
    return ActionErr(ok=False, reason=str(r.get("reason", "error")))

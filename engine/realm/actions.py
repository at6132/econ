"""Player / agent actions — all return {ok: bool, reason?: str}."""

from __future__ import annotations

from typing import Literal, TypedDict, Union

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


def claim_plot(world: World, party: PartyId, plot_id: PlotId) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return ActionErr(ok=False, reason="unknown plot")
    if plot.owner is not None:
        return ActionErr(ok=False, reason="plot already claimed")
    plot.owner = party
    world.parties.add(party)
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

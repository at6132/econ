"""Player / agent actions — all return {ok: bool, reason?: str}."""

from __future__ import annotations

from typing import Any, Literal, TypedDict, Union

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId, PlotId
from realm.plot_logistics import harvest_plot_output_to_party
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
    plot.owner = party
    world.parties.add(party)
    from realm.world import ensure_party_recipe_book

    ensure_party_recipe_book(world, party)
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
    world: World,
    employer: PartyId,
    employee: PartyId,
    signing_bonus_cents: int,
    *,
    wage_per_tick_cents: int = 0,
    wage_interval_ticks: int = 1,
) -> ActionResult:
    """
    Signing bonus to an NPC party; optional recurring wage every ``wage_interval_ticks``.
    """
    if signing_bonus_cents <= 0:
        return ActionErr(ok=False, reason="signing bonus must be positive")
    if wage_per_tick_cents < 0:
        return ActionErr(ok=False, reason="wage_per_tick_cents must be non-negative")
    if wage_interval_ticks < 1:
        return ActionErr(ok=False, reason="wage_interval_ticks must be at least 1")
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
            "signing_bonus_cents": signing_bonus_cents,
            "wage_per_tick_cents": wage_per_tick_cents,
            "wage_interval_ticks": interval,
        }
    )
    world.stub_hires.append(
        {
            "employer": str(employer),
            "employee": str(employee),
            "signing_bonus_cents": signing_bonus_cents,
            "contract_id": cid,
            "tick": world.tick,
            "wage_per_tick_cents": wage_per_tick_cents,
            "wage_interval_ticks": interval,
            "next_wage_tick": world.tick + interval if wage_per_tick_cents > 0 else -1,
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


def revise_route_fee(
    world: World,
    party: PartyId,
    route_key: str,
    new_fee_per_tile_cents: int,
) -> dict[str, Any]:
    """Update the per-tile fee on a route the ``party`` already operates."""
    from realm.route_operators import set_operator_fee

    return set_operator_fee(world, party, route_key, new_fee_per_tile_cents)

"""Five named Tier-2 agent archetypes (Sprint 5 — Phase D).

Each archetype is a deterministic algorithmic agent — no LLM, no natural
language. They play the game with the same API the player uses.

* ``Rothbury & Sons`` (party ``rothbury_and_sons``) — iron Specialist.
* ``Clearwater Mill`` (party ``clearwater_mill``) — timber Specialist.
* ``Prospect Holdings`` (party ``prospect_holdings``) — Flipper.
* ``Cross-Country Logistics`` (party ``cross_country_logistics``) — Shipper.
* ``Meridian Capital`` (party ``meridian_capital``) — Financier.
* (``Kessler Industrial`` is upgraded in-place via the existing
  ``genesis_consolidator`` + ``genesis_forwards`` modules.)

These agents call each other through the standard market and contract
actions, so the player sees their interactions as normal market events.
"""

from __future__ import annotations

import dataclasses
from typing import Final

from realm.actions import (
    buy_survey_report,
    claim_plot,
    list_survey_report,
    survey_plot,
)
from realm.events.event_log import log_event
from realm.genesis.bank import (
    LOAN_CYCLE_TICKS,
    apply_bank_loan,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.economy.markets import place_sell_order
from realm.world.regions import all_region_ids, region_for_plot, route_key
from realm.infrastructure.route_operators import (
    list_route_operators,
    register_route,
    set_operator_fee,
)
from realm.world import World


__all__ = [
    "SPECIALIST_IRON_PARTY_ID",
    "SPECIALIST_TIMBER_PARTY_ID",
    "FLIPPER_PARTY_ID",
    "SHIPPER_PARTY_ID",
    "FINANCIER_PARTY_ID",
    "ARCHETYPE_PARTY_IDS",
    "seed_archetype_agents",
    "tick_archetype_agents",
]


# ───────────────────────── identities ─────────────────────────


SPECIALIST_IRON_PARTY_ID: Final[PartyId] = PartyId("rothbury_and_sons")
SPECIALIST_IRON_DISPLAY_NAME: Final[str] = "Rothbury & Sons"
SPECIALIST_TIMBER_PARTY_ID: Final[PartyId] = PartyId("clearwater_mill")
SPECIALIST_TIMBER_DISPLAY_NAME: Final[str] = "Clearwater Mill"

FLIPPER_PARTY_ID: Final[PartyId] = PartyId("prospect_holdings")
FLIPPER_DISPLAY_NAME: Final[str] = "Prospect Holdings"
FLIPPER_STARTING_CASH_CENTS: Final[int] = 2_000_000  # $20,000

SHIPPER_PARTY_ID: Final[PartyId] = PartyId("cross_country_logistics")
SHIPPER_DISPLAY_NAME: Final[str] = "Cross-Country Logistics"
SHIPPER_STARTING_CASH_CENTS: Final[int] = 500_000

FINANCIER_PARTY_ID: Final[PartyId] = PartyId("meridian_capital")
FINANCIER_DISPLAY_NAME: Final[str] = "Meridian Capital"
FINANCIER_STARTING_CASH_CENTS: Final[int] = 6_000_000  # $60,000

ARCHETYPE_PARTY_IDS: Final[tuple[PartyId, ...]] = (
    SPECIALIST_IRON_PARTY_ID,
    SPECIALIST_TIMBER_PARTY_ID,
    FLIPPER_PARTY_ID,
    SHIPPER_PARTY_ID,
    FINANCIER_PARTY_ID,
)


_TICKS_PER_GAME_DAY: Final[int] = 1440
_SHIPPER_DEFAULT_FEE_CENTS: Final[int] = 3
_SHIPPER_FLOOR_FEE_CENTS: Final[int] = 2
_FLIPPER_REPORT_ASK_STANDARD: Final[int] = 800
_FLIPPER_REPORT_ASK_DEEP: Final[int] = 2_000


# ───────────────────────── helpers ─────────────────────────


def _ensure_party(world: World, party: PartyId, display: str, cash_cents: int) -> bool:
    """Seed a party with display name + cash. Returns True on first creation."""
    if party in world.parties:
        return False
    world.parties.add(party)
    world.reputation[str(party)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(party)] = display
    acct = party_cash_account(party)
    world.ledger.ensure_account(acct)
    if cash_cents > 0:
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=int(cash_cents),
        )
        if isinstance(tr, MoneyErr):
            return False
    return True


def _instance_complete(
    world: World, building_id: str, party: PartyId, plot_id: PlotId
) -> str:
    """Synchronously place a completed building for an archetype party."""
    world.next_building_instance_seq += 1
    instance_id = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": instance_id,
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": building_id,
            "label": f"{building_id} ({world.party_display_names.get(str(party), str(party))})",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    return instance_id


# ───────────────────────── Specialists ─────────────────────────


_SPECIALISTS_SPEC: Final[tuple[dict, ...]] = (
    {
        "party": SPECIALIST_IRON_PARTY_ID,
        "display": SPECIALIST_IRON_DISPLAY_NAME,
        "vertical": "iron",
        "output_material": "iron_ingot",
        "workshop": "foundry",
        "subsurface_field": "iron_ore_grade",
    },
    {
        "party": SPECIALIST_TIMBER_PARTY_ID,
        "display": SPECIALIST_TIMBER_DISPLAY_NAME,
        "vertical": "timber",
        "output_material": "timber",
        "workshop": "wood_shop",
        "subsurface_field": None,  # timber doesn't need subsurface
    },
)


def _pick_specialist_home(
    world: World, spec: dict, exclude: set[str]
) -> PlotId | None:
    """Pick the unowned plot with the strongest subsurface alignment for this vertical.

    Stays away from p-0-0 and the immediate corner (commonly poked by tests
    + UI smoke flows) so the player can still claim those plots themselves.
    """
    field = spec.get("subsurface_field")
    best: tuple[float, int, PlotId] | None = None
    for pid, plot in world.plots.items():
        if plot.owner is not None:
            continue
        if str(pid) in exclude:
            continue
        # Reserve the (0,0) corner for tests / first-claim scenarios.
        if plot.x <= 1 and plot.y <= 1:
            continue
        score = 1.0
        if field:
            score = float(getattr(plot.subsurface, field, 0.0))
        # Tie-break with -(x+y) so timber prefers a plot toward the south-east
        # rather than the (0,0) corner.
        if best is None or (score, plot.x + plot.y) > (best[0], best[1]):
            best = (score, plot.x + plot.y, pid)
    return best[2] if best else None


def _seed_specialist(world: World, spec: dict, exclude_plots: set[str]) -> None:
    party = spec["party"]
    if not _ensure_party(world, party, spec["display"], 1_000_000):
        return
    plot_id = _pick_specialist_home(world, spec, exclude_plots)
    if plot_id is None:
        return
    exclude_plots.add(str(plot_id))
    plot = world.plots[plot_id]
    plot.owner = party
    plot.surveyed = True
    # Max relevant grade so the specialist has a real advantage in their vertical.
    if spec.get("subsurface_field"):
        plot.subsurface = dataclasses.replace(
            plot.subsurface, **{spec["subsurface_field"]: 1.0}
        )
    _instance_complete(world, spec["workshop"], party, plot_id)
    log_event(
        world,
        "specialist_seeded",
        f"{spec['display']} established on {plot_id}, vertical={spec['vertical']}",
        party=str(party),
        plot_id=str(plot_id),
        vertical=spec["vertical"],
    )


def _tick_specialist_list_output(world: World, spec: dict) -> None:
    """Once per game-day, list 2 units of the specialist's output if they have any."""
    party = spec["party"]
    if party not in world.parties:
        return
    mid = MaterialId(spec["output_material"])
    qty_available = world.inventory.qty(party, mid)
    if qty_available <= 0:
        return
    # Match an aggressive but profitable price relative to current spot.
    from realm.economy.pricing import exchange_ask_cents

    spot = int(exchange_ask_cents(mid, world=world))
    price = max(10, int(spot * 96 // 100))  # mild undercut vs exchange
    list_qty = min(2, qty_available)
    place_sell_order(world, party, mid, list_qty, price)


def _tick_specialists(world: World) -> None:
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    for spec in _SPECIALISTS_SPEC:
        _tick_specialist_list_output(world, spec)


# ───────────────────────── Flipper ─────────────────────────


def _seed_flipper(world: World) -> None:
    _ensure_party(world, FLIPPER_PARTY_ID, FLIPPER_DISPLAY_NAME, FLIPPER_STARTING_CASH_CENTS)


def _flipper_state(world: World) -> dict:
    return world.scenario_state.setdefault(
        "flipper_state",
        {"last_acted_tick": -10_000, "plots_claimed_today": 0, "day_marker": -1},
    )


def _flipper_pick_target_plots(world: World, limit: int) -> list[PlotId]:
    """Pick up to ``limit`` unowned, visibly attractive plots (high terrain density).

    Reserves the (0,0) corner for tests / UI smoke flows.
    """
    candidates: list[tuple[float, PlotId]] = []
    for pid, plot in world.plots.items():
        if plot.owner is not None:
            continue
        if plot.x <= 1 and plot.y <= 1:
            continue
        density = float(
            (world.scenario_state.get("population_density") or {}).get(str(pid), 0.0)
        )
        candidates.append((-density, pid))
    candidates.sort()
    return [c[1] for c in candidates[:limit]]


def _tick_flipper(world: World) -> None:
    if FLIPPER_PARTY_ID not in world.parties:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    state = _flipper_state(world)
    targets = _flipper_pick_target_plots(world, limit=2)
    cash_acct = party_cash_account(FLIPPER_PARTY_ID)
    for pid in targets:
        if world.ledger.balance(cash_acct) < 100_000:
            break
        plot = world.plots.get(pid)
        if plot is None or plot.owner is not None:
            continue
        cr = claim_plot(world, FLIPPER_PARTY_ID, pid)
        if not getattr(cr, "ok", True):
            continue
        sr = survey_plot(world, FLIPPER_PARTY_ID, pid)
        if not getattr(sr, "ok", True):
            continue
    # List any reports the flipper owns that aren't already listed.
    ownership = world.scenario_state.get("report_ownership") or {}
    listed_report_ids = {
        str(r.get("report_id"))
        for r in world.intel_listings
        if str(r.get("status")) == "active"
    }
    for rid, owner in list(ownership.items()):
        if str(owner) != str(FLIPPER_PARTY_ID):
            continue
        if str(rid) in listed_report_ids:
            continue
        report = world.survey_reports.get(str(rid))
        if report is None:
            continue
        ask = (
            _FLIPPER_REPORT_ASK_DEEP
            if bool(report.is_deep)
            else _FLIPPER_REPORT_ASK_STANDARD
        )
        r = list_survey_report(world, FLIPPER_PARTY_ID, str(rid), int(ask))
        if r.get("ok"):
            try:
                from realm.genesis.margaux_sprint5 import fire_archetype_observation_beat

                fire_archetype_observation_beat(
                    world,
                    archetype="flipper_listed",
                    report_id=str(rid),
                    plot_id=str(report.plot_id),
                )
            except Exception:
                pass
    state["last_acted_tick"] = int(world.tick)


# ───────────────────────── Shipper ─────────────────────────


def _shipper_depot_plot_for_region(
    world: World, region_id: str, used: set[str]
) -> PlotId | None:
    """First unowned plot inside ``region_id`` not already taken.

    Reserves the (0,0)/(0,1)/(1,0) corner for tests + first-claim flows.
    """
    for pid, plot in world.plots.items():
        if plot.owner is not None:
            continue
        if str(pid) in used:
            continue
        if plot.x <= 1 and plot.y <= 1:
            continue
        if region_for_plot(world, pid) == region_id:
            return pid
    return None


def _seed_shipper(world: World) -> None:
    if SHIPPER_PARTY_ID in world.parties:
        return
    if not _ensure_party(
        world, SHIPPER_PARTY_ID, SHIPPER_DISPLAY_NAME, SHIPPER_STARTING_CASH_CENTS
    ):
        return
    # Two vessels — enough to register every coastal route.
    try:
        world.inventory.add(SHIPPER_PARTY_ID, MaterialId("vessel"), 2)
    except (AttributeError, ValueError, MatterErr):
        pass
    # Claim one depot plot per region; place a dock on each so the shipper can
    # register on routes touching ANY region.
    region_to_depot: dict[str, PlotId] = {}
    used: set[str] = set()
    for region_id in all_region_ids():
        depot = _shipper_depot_plot_for_region(world, region_id, used)
        if depot is None:
            continue
        world.plots[depot].owner = SHIPPER_PARTY_ID
        used.add(str(depot))
        _instance_complete(world, "dock", SHIPPER_PARTY_ID, depot)
        region_to_depot[region_id] = depot
    world.scenario_state["cross_country_depots"] = {
        rid: str(pid) for rid, pid in region_to_depot.items()
    }
    # Register on every distinct region pair using a depot that lies in one of
    # the pair's endpoints.
    regions = all_region_ids()
    for i, ra in enumerate(regions):
        for rb in regions[i + 1 :]:
            home = region_to_depot.get(ra) or region_to_depot.get(rb)
            if home is None:
                continue
            register_route(
                world,
                SHIPPER_PARTY_ID,
                home,
                ra,
                rb,
                _SHIPPER_DEFAULT_FEE_CENTS,
            )


def _tick_shipper(world: World) -> None:
    """Drop fee to floor on any route where another operator joined; reclaim missing ones."""
    if SHIPPER_PARTY_ID not in world.parties:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    depot_map_raw = world.scenario_state.get("cross_country_depots") or {}
    depot_map: dict[str, PlotId] = {
        str(rid): PlotId(str(pid)) for rid, pid in depot_map_raw.items()
    }
    regions = all_region_ids()
    for i, ra in enumerate(regions):
        for rb in regions[i + 1 :]:
            key = route_key(ra, rb)
            ops = list_route_operators(world, key)
            mine = next(
                (o for o in ops if str(o.get("operator_party")) == str(SHIPPER_PARTY_ID)),
                None,
            )
            if mine is None:
                home = depot_map.get(ra) or depot_map.get(rb)
                if home is None:
                    continue
                register_route(
                    world,
                    SHIPPER_PARTY_ID,
                    home,
                    ra,
                    rb,
                    _SHIPPER_DEFAULT_FEE_CENTS,
                )
                continue
            current_fee = int(mine.get("fee_per_tile_cents", 0))
            competitor = any(
                str(o.get("operator_party")) != str(SHIPPER_PARTY_ID) for o in ops
            )
            if competitor and current_fee > _SHIPPER_FLOOR_FEE_CENTS:
                set_operator_fee(world, SHIPPER_PARTY_ID, key, _SHIPPER_FLOOR_FEE_CENTS)


# ───────────────────────── Financier ─────────────────────────


_FINANCIER_RATE_BPS: Final[int] = 900  # 9 %/cycle
_FINANCIER_MIN_REVENUE_PER_DAY: Final[int] = 30_000  # 300¢ → settler made $3/day
_FINANCIER_MAX_BORROWER_CASH: Final[int] = 300_000  # $3,000
_FINANCIER_PRINCIPAL_CENTS: Final[int] = 200_000  # $2,000 standard offer


def _seed_financier(world: World) -> None:
    _ensure_party(
        world,
        FINANCIER_PARTY_ID,
        FINANCIER_DISPLAY_NAME,
        FINANCIER_STARTING_CASH_CENTS,
    )


def _settler_daily_revenue(world: World, party: PartyId) -> int:
    """Rough proxy: sum of recent market_match credits to ``party`` in the last day."""
    cutoff = int(world.tick) - _TICKS_PER_GAME_DAY
    total = 0
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < cutoff:
            break
        if ev.get("kind") != "market_match":
            continue
        if str(ev.get("seller", "")) != str(party):
            continue
        try:
            qty = int(ev.get("qty", 0))
            unit = int(ev.get("price_per_unit_cents", 0))
        except (TypeError, ValueError):
            continue
        total += qty * unit
    return total


def _financier_state(world: World) -> dict:
    return world.scenario_state.setdefault(
        "financier_state", {"offered_to": [], "last_acted_tick": -10_000}
    )


def _tick_financier(world: World) -> None:
    if FINANCIER_PARTY_ID not in world.parties:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    state = _financier_state(world)
    offered: list[str] = list(state.get("offered_to") or [])
    funds = world.ledger.balance(party_cash_account(FINANCIER_PARTY_ID))
    if funds < _FINANCIER_PRINCIPAL_CENTS:
        return
    for party in list(world.parties):
        sp = str(party)
        if not sp.startswith("settler_"):
            continue
        if sp in offered:
            continue
        cash = world.ledger.balance(party_cash_account(party))
        if cash > _FINANCIER_MAX_BORROWER_CASH:
            continue
        revenue = _settler_daily_revenue(world, party)
        if revenue < _FINANCIER_MIN_REVENUE_PER_DAY:
            continue
        r = apply_bank_loan(
            world,
            party,
            _FINANCIER_PRINCIPAL_CENTS,
            3,
            collateral_plot_id=None,
            lender=FINANCIER_PARTY_ID,
            rate_bps_override=_FINANCIER_RATE_BPS,
            max_principal_override=_FINANCIER_PRINCIPAL_CENTS,
            cycle_ticks=LOAN_CYCLE_TICKS,
        )
        if r.get("ok"):
            offered.append(sp)
            log_event(
                world,
                "meridian_loan_offered",
                f"Meridian Capital extended a $2,000 loan to {party}",
                lender=str(FINANCIER_PARTY_ID),
                borrower=sp,
            )
            funds -= _FINANCIER_PRINCIPAL_CENTS
            if funds < _FINANCIER_PRINCIPAL_CENTS:
                break
    state["offered_to"] = offered
    state["last_acted_tick"] = int(world.tick)


# ───────────────────────── Archetype cross-deals ─────────────────────────


def _tick_archetype_interactions(world: World) -> None:
    """Once per game-day, have the iron Specialist buy any standard-grade report
    the Flipper has listed. This produces an observable archetype-to-archetype
    transaction without requiring full route flow simulation."""
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    if SPECIALIST_IRON_PARTY_ID not in world.parties:
        return
    cash = world.ledger.balance(party_cash_account(SPECIALIST_IRON_PARTY_ID))
    if cash < _FLIPPER_REPORT_ASK_STANDARD:
        return
    for listing in list(world.intel_listings):
        if listing.get("status") != "active":
            continue
        if str(listing.get("seller", "")) != str(FLIPPER_PARTY_ID):
            continue
        if int(listing.get("ask_price_cents", 0)) > cash:
            continue
        r = buy_survey_report(
            world, SPECIALIST_IRON_PARTY_ID, str(listing["listing_id"])
        )
        if r.get("ok"):
            return  # one per game-day is plenty


# ───────────────────────── public seeding + tick ─────────────────────────


def seed_archetype_agents(world: World) -> None:
    """Seed all five archetype parties into a Genesis world. Idempotent."""
    if world.scenario_id != "genesis":
        return
    used: set[str] = set()
    for spec in _SPECIALISTS_SPEC:
        _seed_specialist(world, spec, used)
    _seed_flipper(world)
    _seed_shipper(world)
    _seed_financier(world)


def tick_archetype_agents(world: World) -> None:
    """Daily archetype action loops. Called from ``advance_tick``."""
    if world.scenario_id != "genesis":
        return
    _tick_specialists(world)
    _tick_flipper(world)
    _tick_shipper(world)
    _tick_financier(world)
    _tick_archetype_interactions(world)

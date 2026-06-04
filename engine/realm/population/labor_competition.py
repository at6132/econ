"""Labor competition — poaching, island wage unrest, and employer-funded training."""

from __future__ import annotations

from typing import Any, Final

from realm.agents.settler_identity import get_settler_personality
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.population.employment import (
    DEFAULT_WAGE_PER_GAME_DAY_CENTS,
    MIN_WAGE_PER_GAME_DAY_CENTS,
    _opening_for_employment,
    _plot_island_id,
)
from realm.population.laborers import TICKS_PER_GAME_DAY, LaborerNPC
from realm.world import World

GREED_POACH_THRESHOLD: Final[float] = 0.65
SKILLED_LABOR_MIN_LEVEL: Final[int] = 40
POACH_WAGE_PREMIUM_BPS: Final[int] = 12_500  # 125 % of current wage
POACH_REPUTATION_MIN: Final[float] = 0.4
UNREST_WAGE_RATIO_TRIGGER: Final[float] = 0.6
UNREST_CLEAR_WAGE_PREMIUM: Final[float] = 1.15
UNREST_YIELD_MULTIPLIER: Final[float] = 0.7
TRAINING_MIN_SETTLER_CASH_CENTS: Final[int] = 200_000
TRAINING_COST_PER_DAY_CENTS: Final[int] = 500
TRAINING_SKILL_GAIN_PER_DAY: Final[int] = 3
POACH_INTERVAL_GAME_DAYS: Final[int] = 3
WAGE_AVG_LOOKBACK_DAYS: Final[int] = 30
WAGE_PEAK_LOOKBACK_DAYS: Final[int] = 90

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_TICKS_POACH_INTERVAL = POACH_INTERVAL_GAME_DAYS * TICKS_PER_GAME_DAY


__all__ = [
    "tick_labor_poaching",
    "tick_labor_organizing",
    "tick_labor_training",
    "labor_unrest_yield_multiplier",
    "island_has_labor_unrest",
]


def _party_label(world: World, party: PartyId) -> str:
    return str(world.party_display_names.get(str(party), party))


def _normalized_reputation_score(world: World, party: PartyId) -> float:
    rep = world.reputation.get(str(party), {})
    if not isinstance(rep, dict):
        return 0.5
    honored = int(rep.get("honored", 0))
    breached = int(rep.get("breached", 0))
    total = honored + breached
    if total <= 0:
        return 0.5
    return max(0.0, (honored - breached) / float(total))


def _laborer_current_wage_cents(world: World, lab: LaborerNPC) -> int:
    if lab.employment_contract:
        op = _opening_for_employment(world, lab.employment_contract)
        if op is not None:
            wage = int(op.wage_per_day_cents)
            if bool(getattr(op, "cpi_indexed", False)):
                from realm.economy.cpi import cpi_multiplier

                wage = max(1, int(round(wage * float(cpi_multiplier(world)))))
            return wage
    wpd = int(getattr(lab, "wage_per_day_cents", 0) or 0)
    return wpd if wpd > 0 else DEFAULT_WAGE_PER_GAME_DAY_CENTS


def _max_skill_level(lab: LaborerNPC) -> int:
    levels = getattr(lab, "skill_levels", None) or {}
    if not levels:
        return int(getattr(lab, "skill_level", 0))
    return max(int(v) for v in levels.values())


def _primary_recipe_for_laborer(world: World, lab: LaborerNPC) -> str:
    levels = getattr(lab, "skill_levels", None) or {}
    if levels:
        return max(levels, key=lambda k: int(levels[k]))
    return "mine_ore"


def _island_wage_stats(
    world: World, *, since_tick: int
) -> tuple[dict[int, list[int]], dict[int, int]]:
    """Return per-island wage samples since ``since_tick`` and counts for averaging."""
    by_island: dict[int, list[int]] = {}
    for ev in world.event_log:
        tick = int(ev.get("tick", 0))
        if tick < since_tick:
            continue
        if ev.get("kind") != "laborer_wage_paid":
            continue
        plot_raw = ev.get("plot_id")
        if not plot_raw:
            continue
        island = _plot_island_id(world, PlotId(str(plot_raw)))
        if island < 0:
            continue
        amount = int(ev.get("amount_cents", 0) or 0)
        if amount <= 0:
            continue
        by_island.setdefault(island, []).append(amount)
    return by_island, {k: len(v) for k, v in by_island.items()}


def _island_average_wage_cents(world: World, island_id: int, *, lookback_days: int) -> int:
    since = int(world.tick) - lookback_days * TICKS_PER_GAME_DAY
    samples, _ = _island_wage_stats(world, since_tick=since)
    wages = samples.get(int(island_id), [])
    if not wages:
        return 0
    return int(sum(wages) // len(wages))


def _island_peak_wage_cents(world: World, island_id: int, *, lookback_days: int) -> int:
    since = int(world.tick) - lookback_days * TICKS_PER_GAME_DAY
    samples, _ = _island_wage_stats(world, since_tick=since)
    wages = samples.get(int(island_id), [])
    if not wages:
        return 0
    return max(wages)


def island_has_labor_unrest(world: World, island_id: int) -> bool:
    raw = world.scenario_state.get("labor_unrest") or {}
    if not isinstance(raw, dict):
        return False
    return bool(raw.get(str(int(island_id))) or raw.get(int(island_id)))


def labor_unrest_yield_multiplier(world: World, island_id: int) -> float:
    if island_has_labor_unrest(world, island_id):
        return UNREST_YIELD_MULTIPLIER
    return 1.0


def _poach_offers_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("labor_poach_offers", {})
    if not isinstance(raw, dict):
        world.scenario_state["labor_poach_offers"] = {}
        raw = world.scenario_state["labor_poach_offers"]
    return raw


def _training_contracts_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("training_contracts", {})
    if not isinstance(raw, dict):
        world.scenario_state["training_contracts"] = {}
        raw = world.scenario_state["training_contracts"]
    return raw


def _unrest_store(world: World) -> dict[str, bool]:
    raw = world.scenario_state.setdefault("labor_unrest", {})
    if not isinstance(raw, dict):
        world.scenario_state["labor_unrest"] = {}
        raw = world.scenario_state["labor_unrest"]
    return raw


def _execute_poach(
    world: World,
    *,
    lab: LaborerNPC,
    poacher: PartyId,
    old_employer: PartyId,
    new_wage_cents: int,
) -> None:
    old_op = (
        _opening_for_employment(world, lab.employment_contract)
        if lab.employment_contract
        else None
    )
    if old_op is not None:
        old_op.filled_by = None
    log_event(
        world,
        "wage_unpaid_quit",
        f"{lab.display_name} quit {old_employer}: poached",
        laborer_id=lab.laborer_id,
        employer=str(old_employer),
        opening_id=lab.employment_contract or "",
        reason="poached",
    )
    lab.employer = poacher
    lab.employment_contract = None
    lab.wage_per_day_cents = int(new_wage_cents)
    log_event(
        world,
        "laborer_hired",
        f"{lab.display_name} hired by {poacher} (poached, ${new_wage_cents/100:.2f}/day)",
        employer=str(poacher),
        laborer_id=lab.laborer_id,
        wage_per_day_cents=int(new_wage_cents),
        source="poach",
    )
    poacher_name = _party_label(world, poacher)
    old_name = _party_label(world, old_employer)
    log_event(
        world,
        "world_feed",
        f"{poacher_name} poached {lab.display_name} from {old_name} "
        f"at ${new_wage_cents/100:.2f}/day",
        poacher=str(poacher),
        old_employer=str(old_employer),
        laborer_id=lab.laborer_id,
        wage_per_day_cents=int(new_wage_cents),
    )


def tick_labor_poaching(world: World) -> dict[str, int]:
    """Every 3 game-days: greedy settlers bid 25 % above rivals for skilled labor."""
    stats = {"offers": 0, "accepted": 0}
    if world.scenario_id != "genesis":
        return stats
    now = int(world.tick)
    if now <= 0 or now % _TICKS_POACH_INTERVAL != 0:
        return stats

    offers = _poach_offers_store(world)
    offers.clear()

    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")),
        key=str,
    )
    for poacher in settlers:
        personality = get_settler_personality(world, poacher)
        if personality is None or float(personality.greed_index) <= GREED_POACH_THRESHOLD:
            continue
        poacher_island: int | None = None
        for plot in world.plots.values():
            if plot.owner == poacher:
                isl = _plot_island_id(world, plot.plot_id)
                if isl >= 0:
                    poacher_island = isl
                    break
        if poacher_island is None:
            continue
        if _normalized_reputation_score(world, poacher) <= POACH_REPUTATION_MIN:
            continue
        poacher_cash = world.ledger.balance(party_cash_account(poacher))
        for lab in sorted(world.laborers.values(), key=lambda x: x.laborer_id):
            if lab.employer is None or lab.employer == poacher:
                continue
            if int(lab.island_id) != int(poacher_island):
                continue
            if not str(lab.employer).startswith("settler_"):
                continue
            if _max_skill_level(lab) < SKILLED_LABOR_MIN_LEVEL:
                continue
            current_wage = _laborer_current_wage_cents(world, lab)
            offered = max(
                MIN_WAGE_PER_GAME_DAY_CENTS,
                int(current_wage * POACH_WAGE_PREMIUM_BPS // 10_000),
            )
            if current_wage >= offered:
                continue
            if poacher_cash < offered:
                continue
            offers[lab.laborer_id] = {
                "poacher": str(poacher),
                "old_employer": str(lab.employer),
                "offered_wage_cents": int(offered),
                "posted_tick": now,
            }
            stats["offers"] += 1
            if offered > current_wage and _normalized_reputation_score(world, poacher) > POACH_REPUTATION_MIN:
                _execute_poach(
                    world,
                    lab=lab,
                    poacher=poacher,
                    old_employer=PartyId(str(lab.employer)),
                    new_wage_cents=offered,
                )
                stats["accepted"] += 1
                offers.pop(lab.laborer_id, None)
    return stats


def _maybe_clear_island_unrest(world: World, island_id: int, avg_wage: int) -> bool:
    if avg_wage <= 0:
        return False
    threshold = int(avg_wage * UNREST_CLEAR_WAGE_PREMIUM)
    unrest = _unrest_store(world)
    key = str(int(island_id))
    if not unrest.get(key):
        return False
    cleared = False
    for lab in world.laborers.values():
        if int(lab.island_id) != int(island_id):
            continue
        if lab.employer is None or not str(lab.employer).startswith("settler_"):
            continue
        if _laborer_current_wage_cents(world, lab) >= threshold:
            unrest.pop(key, None)
            log_event(
                world,
                "world_feed",
                f"Labor unrest eased on island {island_id}: "
                f"{_party_label(world, lab.employer)} raised wages.",
                island_id=int(island_id),
                employer=str(lab.employer),
                wage_cents=_laborer_current_wage_cents(world, lab),
            )
            cleared = True
            break
    since = int(world.tick) - TICKS_PER_GAME_DAY
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < since:
            break
        if ev.get("kind") not in ("job_posted", "laborer_hired"):
            continue
        wage = int(ev.get("wage_per_day_cents", 0) or 0)
        if wage < threshold:
            continue
        employer = str(ev.get("employer", ""))
        if not employer.startswith("settler_"):
            continue
        unrest.pop(key, None)
        log_event(
            world,
            "world_feed",
            f"Labor unrest eased on island {island_id}: {employer} posted higher wages.",
            island_id=int(island_id),
            employer=employer,
            wage_cents=wage,
        )
        cleared = True
        break
    return cleared


def tick_labor_organizing(world: World) -> dict[str, int]:
    """Weekly: depressed island wages trigger production slowdown until pay recovers."""
    stats = {"unrest_set": 0, "unrest_cleared": 0}
    if world.scenario_id != "genesis":
        return stats
    now = int(world.tick)
    if now <= 0 or now % _TICKS_PER_GAME_WEEK != 0:
        return stats

    plot_islands = world.scenario_state.get("plot_islands") or {}
    islands = sorted({int(v) for v in plot_islands.values()})
    unrest = _unrest_store(world)

    for island_id in islands:
        avg_wage = _island_average_wage_cents(
            world, island_id, lookback_days=WAGE_AVG_LOOKBACK_DAYS
        )
        peak_wage = _island_peak_wage_cents(
            world, island_id, lookback_days=WAGE_PEAK_LOOKBACK_DAYS
        )
        if _maybe_clear_island_unrest(world, island_id, avg_wage):
            stats["unrest_cleared"] += 1
            continue
        if peak_wage <= 0 or avg_wage <= 0:
            continue
        if float(avg_wage) / float(peak_wage) >= UNREST_WAGE_RATIO_TRIGGER:
            continue
        key = str(int(island_id))
        if not unrest.get(key):
            unrest[key] = True
            stats["unrest_set"] += 1
            log_event(
                world,
                "labor_unrest",
                f"Island {island_id} labor unrest: avg wage ${avg_wage/100:.2f} "
                f"vs peak ${peak_wage/100:.2f}",
                island_id=int(island_id),
                avg_wage_cents=avg_wage,
                peak_wage_cents=peak_wage,
            )
    return stats


def _maybe_start_training_contract(world: World, settler: PartyId) -> None:
    contracts = _training_contracts_store(world)
    if str(settler) in contracts:
        return
    cash = world.ledger.balance(party_cash_account(settler))
    if cash < TRAINING_MIN_SETTLER_CASH_CENTS:
        return
    candidates: list[tuple[int, LaborerNPC]] = []
    for lab in world.laborers.values():
        if lab.employer != settler:
            continue
        candidates.append((_max_skill_level(lab), lab))
    if not candidates:
        return
    candidates.sort(key=lambda row: (-row[0], row[1].laborer_id))
    lab = candidates[0][1]
    contracts[str(settler)] = {
        "laborer_id": lab.laborer_id,
        "primary_recipe": _primary_recipe_for_laborer(world, lab),
        "started_tick": int(world.tick),
    }


def tick_labor_training(world: World) -> dict[str, int]:
    """Daily: wealthy settlers fund accelerated skill training for key laborers."""
    stats = {"trained": 0, "cancelled": 0, "events": 0}
    if world.scenario_id != "genesis":
        return stats
    now = int(world.tick)
    if now <= 0 or now % TICKS_PER_GAME_DAY != 0:
        return stats

    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")),
        key=str,
    )
    for settler in settlers:
        _maybe_start_training_contract(world, settler)

    contracts = _training_contracts_store(world)
    weekly_log = now % _TICKS_PER_GAME_WEEK == 0
    to_drop: list[str] = []
    for settler_s, row in sorted(contracts.items()):
        if not isinstance(row, dict):
            to_drop.append(settler_s)
            continue
        lid = str(row.get("laborer_id", ""))
        recipe_id = str(row.get("primary_recipe", ""))
        lab = world.laborers.get(lid)
        settler = PartyId(settler_s)
        if lab is None or lab.employer != settler:
            to_drop.append(settler_s)
            stats["cancelled"] += 1
            continue
        cash = world.ledger.balance(party_cash_account(settler))
        if cash < TRAINING_COST_PER_DAY_CENTS:
            to_drop.append(settler_s)
            stats["cancelled"] += 1
            continue
        tr = world.ledger.transfer(
            debit=party_cash_account(settler),
            credit=system_reserve_account(),
            amount_cents=TRAINING_COST_PER_DAY_CENTS,
        )
        if isinstance(tr, MoneyErr):
            to_drop.append(settler_s)
            stats["cancelled"] += 1
            continue
        if not recipe_id:
            recipe_id = _primary_recipe_for_laborer(world, lab)
            row["primary_recipe"] = recipe_id
        levels = getattr(lab, "skill_levels", None)
        if levels is None:
            lab.skill_levels = {}
            levels = lab.skill_levels
        from realm.population.laborer_lifecycle import SKILL_CAP

        cur = int(levels.get(recipe_id, 0))
        if cur < SKILL_CAP:
            levels[recipe_id] = min(SKILL_CAP, cur + TRAINING_SKILL_GAIN_PER_DAY)
            stats["trained"] += 1
        if weekly_log:
            log_event(
                world,
                "laborer_trained",
                f"{_party_label(world, settler)} trained {lab.display_name} "
                f"on {recipe_id} (+{TRAINING_SKILL_GAIN_PER_DAY})",
                settler=settler_s,
                laborer_id=lid,
                recipe_id=recipe_id,
                skill_level=int(levels.get(recipe_id, 0)),
            )
            stats["events"] += 1
    for key in to_drop:
        contracts.pop(key, None)
    return stats

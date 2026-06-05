"""Laborer lifecycle depth — health, savings, skills, reproduction.

Extends :class:`~realm.population.laborers.LaborerNPC` with daily health
pressure, wage savings, recipe skills, and weekly reproduction pairing.
All new fields use ``getattr`` defaults so saves without them load cleanly.
"""

from __future__ import annotations

from typing import Final

from realm.core.ids import PartyId, PlotId
from realm.core.ledger import AccountId, MoneyErr, system_reserve_account
from realm.events.event_log import log_event
from realm.population.laborers import (
    TICKS_PER_GAME_DAY,
    LaborerNPC,
    _retire_laborer,
    laborer_cash_account,
)
from realm.world import World


BASELINE_HEALTH_DECAY_PER_DAY: Final[float] = 0.003
FOOD_HEALTH_BONUS_PER_DAY: Final[float] = 0.012
STRESS_HEALTH_PENALTY: Final[float] = 0.010
HEALTH_LOW_OUTPUT_THRESHOLD: Final[float] = 0.30
HEALTH_LOW_OUTPUT_MULTIPLIER: Final[float] = 0.50
WAGE_SAVINGS_FRACTION_BPS: Final[int] = 2_000  # 20 %
REPRODUCTION_HEALTH_MIN: Final[float] = 0.40
REPRODUCTION_SAVINGS_MIN_CENTS: Final[int] = 500
BIRTH_CHANCE_PER_WEEK: Final[float] = 0.25
SKILL_CAP: Final[int] = 100
SKILL_YIELD_THRESHOLD: Final[int] = 50
FOOD_HEALTH_MATERIALS: Final[frozenset[str]] = frozenset(
    {"grain", "smoked_fish", "bread", "fish"}
)


__all__ = [
    "BASELINE_HEALTH_DECAY_PER_DAY",
    "FOOD_HEALTH_BONUS_PER_DAY",
    "STRESS_HEALTH_PENALTY",
    "HEALTH_LOW_OUTPUT_THRESHOLD",
    "HEALTH_LOW_OUTPUT_MULTIPLIER",
    "WAGE_SAVINGS_FRACTION_BPS",
    "REPRODUCTION_HEALTH_MIN",
    "REPRODUCTION_SAVINGS_MIN_CENTS",
    "BIRTH_CHANCE_PER_WEEK",
    "SKILL_CAP",
    "SKILL_YIELD_THRESHOLD",
    "FOOD_HEALTH_MATERIALS",
    "laborer_savings_account",
    "laborer_health_output_multiplier",
    "skill_yield_multiplier_for_laborer",
    "laborers_at_workplace",
    "tick_laborer_health",
    "tick_laborer_savings",
    "apply_wage_savings_split",
    "try_absorb_unpaid_wage_from_savings",
    "tick_laborer_skills",
    "tick_laborer_reproduction",
]


def laborer_savings_account(laborer_id: str) -> AccountId:
    return AccountId(f"cash:lab:sav:{laborer_id}")


def _sync_savings_balance(world: World, lab: LaborerNPC) -> int:
    acct = laborer_savings_account(lab.laborer_id)
    world.ledger.ensure_account(acct)
    bal = world.ledger.balance(acct)
    lab.savings_cents = int(bal)
    return int(bal)


def laborer_health_output_multiplier(lab: LaborerNPC) -> float:
    health = float(getattr(lab, "health", 1.0))
    if health < HEALTH_LOW_OUTPUT_THRESHOLD:
        return HEALTH_LOW_OUTPUT_MULTIPLIER
    return 1.0


def skill_yield_multiplier_for_laborer(lab: LaborerNPC, recipe_id: str) -> float:
    levels = getattr(lab, "skill_levels", None) or {}
    skill = int(levels.get(str(recipe_id), 0))
    if skill < SKILL_YIELD_THRESHOLD:
        return 1.0
    return 1.0 + min(SKILL_CAP, skill) / 200.0


def laborers_at_workplace(
    world: World, employer: PartyId, plot_id: PlotId
) -> list[LaborerNPC]:
    """Laborers hired to work at ``plot_id`` for ``employer``."""
    from realm.population.employment import _opening_for_employment

    out: list[LaborerNPC] = []
    pid_s = str(plot_id)
    for lab in world.laborers.values():
        if lab.employer != employer:
            continue
        contract = getattr(lab, "employment_contract", None)
        if contract:
            op = _opening_for_employment(world, str(contract))
            if op is not None and str(op.plot_id) == pid_s:
                out.append(lab)
                continue
        if int(getattr(lab, "wage_per_day_cents", 0) or 0) > 0:
            if str(getattr(lab, "home_plot_id", "")) == pid_s:
                out.append(lab)
    return out


def tick_laborer_health(world: World) -> dict[str, int]:
    """Daily health pass: aging, food bonus, stress, retirement at zero health."""
    stats = {"processed": 0, "retired": 0}
    if not world.laborers:
        return stats
    now = int(world.tick)
    if now <= 0 or now % TICKS_PER_GAME_DAY != 0:
        return stats
    since_day = now - TICKS_PER_GAME_DAY
    plot_to_town: dict[str, str] = {}
    for town_id, town in world.towns.items():
        for plot in town.store_plots:
            plot_to_town[str(plot)] = town_id
    towns_with_food: set[str] = set()
    stressed_laborers: set[str] = set()
    stress_cutoff = now - 3 * TICKS_PER_GAME_DAY
    for ev in reversed(world.event_log):
        tick = int(ev.get("tick", 0))
        if tick < stress_cutoff:
            break
        kind = ev.get("kind")
        if kind == "wage_unpaid_quit":
            stressed_laborers.add(str(ev.get("laborer_id", "")))
        if tick < since_day:
            continue
        if kind != "store_purchase":
            continue
        mat = str(ev.get("material", ""))
        if mat not in FOOD_HEALTH_MATERIALS:
            continue
        town_id = plot_to_town.get(str(ev.get("plot_id", "")))
        if town_id is not None:
            towns_with_food.add(town_id)
    retired_ids: list[str] = []
    for lab in world.laborers.values():
        health = float(getattr(lab, "health", 1.0))
        health -= BASELINE_HEALTH_DECAY_PER_DAY
        town_id = getattr(lab, "home_town", None)
        if town_id and str(town_id) in towns_with_food:
            health += FOOD_HEALTH_BONUS_PER_DAY
        if lab.laborer_id in stressed_laborers:
            health -= STRESS_HEALTH_PENALTY
        lab.health = max(0.0, min(1.0, health))
        stats["processed"] += 1
        if lab.health <= 0.0:
            retired_ids.append(lab.laborer_id)
    for lid in retired_ids:
        lab = world.laborers.get(lid)
        if lab is None:
            continue
        _retire_laborer(world, lab)
        stats["retired"] += 1
    return stats


def apply_wage_savings_split(world: World, lab: LaborerNPC, wage_cents: int) -> int:
    """Move 20 % of a wage payment from spendable cash into savings."""
    if wage_cents <= 0:
        return 0
    savings_part = int(wage_cents * WAGE_SAVINGS_FRACTION_BPS // 10_000)
    if savings_part <= 0:
        lab.cash_cents = world.ledger.balance(laborer_cash_account(lab.laborer_id))
        return 0
    sav_acct = laborer_savings_account(lab.laborer_id)
    world.ledger.ensure_account(sav_acct)
    tr = world.ledger.transfer(
        debit=laborer_cash_account(lab.laborer_id),
        credit=sav_acct,
        amount_cents=savings_part,
    )
    if isinstance(tr, MoneyErr):
        return 0
    lab.cash_cents = world.ledger.balance(laborer_cash_account(lab.laborer_id))
    _sync_savings_balance(world, lab)
    return savings_part


def try_absorb_unpaid_wage_from_savings(
    world: World, lab: LaborerNPC, wage_cents: int
) -> bool:
    """Cover one missed wage from savings so the laborer does not quit."""
    if wage_cents <= 0:
        return True
    sav_acct = laborer_savings_account(lab.laborer_id)
    world.ledger.ensure_account(sav_acct)
    bal = _sync_savings_balance(world, lab)
    if bal < wage_cents:
        return False
    tr = world.ledger.transfer(
        debit=sav_acct,
        credit=system_reserve_account(),
        amount_cents=int(wage_cents),
    )
    if isinstance(tr, MoneyErr):
        return False
    _sync_savings_balance(world, lab)
    log_event(
        world,
        "laborer_savings_wage_cover",
        f"{lab.display_name} covered one day's wage from savings",
        laborer_id=lab.laborer_id,
        wage_cents=int(wage_cents),
    )
    return True


def tick_laborer_savings(world: World) -> dict[str, int]:
    """Sync savings mirrors after the daily wage pass."""
    stats = {"synced": 0}
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return stats
    for lab in world.laborers.values():
        _sync_savings_balance(world, lab)
        stats["synced"] += 1
    return stats


def _workplace_laborer_index(
    world: World,
) -> dict[tuple[str, str], LaborerNPC]:
    """Map (employer, plot_id) → primary laborer at that workplace."""
    from realm.population.employment import _opening_for_employment

    index: dict[tuple[str, str], LaborerNPC] = {}
    for lab in world.laborers.values():
        if lab.employer is None:
            continue
        plot_id: str | None = None
        contract = getattr(lab, "employment_contract", None)
        if contract:
            op = _opening_for_employment(world, str(contract))
            if op is not None:
                plot_id = str(op.plot_id)
        if plot_id is None:
            continue
        key = (str(lab.employer), plot_id)
        if key not in index or lab.laborer_id < index[key].laborer_id:
            index[key] = lab
    return index


def increment_laborer_skill_for_production(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    recipe_id: str,
    *,
    workplace_index: dict[tuple[str, str], LaborerNPC] | None = None,
) -> bool:
    """Bump one laborer's recipe skill for a completed production cycle."""
    if workplace_index is not None:
        lab = workplace_index.get((str(party), str(plot_id)))
    else:
        workers = laborers_at_workplace(world, party, plot_id)
        lab = workers[0] if workers else None
    if lab is None:
        return False
    levels = getattr(lab, "skill_levels", None)
    if levels is None:
        lab.skill_levels = {}
        levels = lab.skill_levels
    cur = int(levels.get(recipe_id, 0))
    if cur >= SKILL_CAP:
        return False
    levels[recipe_id] = min(SKILL_CAP, cur + 1)
    return True


def tick_laborer_skills(world: World) -> dict[str, int]:
    """Process production completions queued during ``tick_production``."""
    stats = {"skilled": 0}
    pending = world.scenario_state.pop("laborer_skill_pending", None)
    if not pending:
        return stats
    if not isinstance(pending, list):
        return stats
    workplace_index = _workplace_laborer_index(world)
    for item in pending:
        if not isinstance(item, dict):
            continue
        party = PartyId(str(item.get("party", "")))
        plot_id = PlotId(str(item.get("plot_id", "")))
        recipe_id = str(item.get("recipe_id", ""))
        if not recipe_id:
            continue
        if increment_laborer_skill_for_production(
            world, party, plot_id, recipe_id, workplace_index=workplace_index
        ):
            stats["skilled"] += 1
    return stats


def _spawn_laborer_child(
    world: World, parent_a: LaborerNPC, parent_b: LaborerNPC, town_id: str
) -> str:
    from realm.genesis.laborer_names import generate_laborer_name

    town = world.towns.get(town_id)
    if town is None:
        raise RuntimeError(f"unknown town {town_id}")
    next_seq = int(world.scenario_state.setdefault("next_laborer_seq", 1))
    lid = f"lab_{next_seq:05d}"
    world.scenario_state["next_laborer_seq"] = next_seq + 1
    rng = world.rng(f"birth_name:{lid}:{world.tick}")
    name = generate_laborer_name(rng)
    home_plot = town.center_plot
    if town.residential_plots:
        home_plot = town.residential_plots[0]
    lab = LaborerNPC(
        laborer_id=lid,
        display_name=name,
        island_id=int(town.island_id),
        home_plot_id=home_plot,
        home_town=town_id,
        health=1.0,
        savings_cents=0,
        skill_levels={},
        birth_tick=int(world.tick),
        last_needs_tick=int(world.tick),
    )
    world.ledger.ensure_account(laborer_cash_account(lid))
    world.laborers[lid] = lab
    parent_a.children_born = int(getattr(parent_a, "children_born", 0)) + 1
    parent_b.children_born = int(getattr(parent_b, "children_born", 0)) + 1
    log_event(
        world,
        "laborer_born",
        f"{name} born to {parent_a.display_name} and {parent_b.display_name} in {town.name}",
        laborer_id=lid,
        parent_a=parent_a.laborer_id,
        parent_b=parent_b.laborer_id,
        town_id=town_id,
        birth_tick=int(world.tick),
    )
    return lid


def tick_laborer_reproduction(world: World) -> dict[str, int]:
    """Weekly pairing and birth rolls within each town."""
    stats = {"paired": 0, "born": 0}
    if not world.laborers or not world.towns:
        return stats
    now = int(world.tick)
    if now <= 0 or now % (7 * TICKS_PER_GAME_DAY) != 0:
        return stats
    for town_id in sorted(world.towns.keys()):
        eligible: list[LaborerNPC] = []
        for lab in world.laborers.values():
            if getattr(lab, "home_town", None) != town_id:
                continue
            if getattr(lab, "partner_id", None) is not None:
                continue
            health = float(getattr(lab, "health", 1.0))
            savings = int(getattr(lab, "savings_cents", 0) or 0)
            if health < REPRODUCTION_HEALTH_MIN:
                continue
            if savings < REPRODUCTION_SAVINGS_MIN_CENTS:
                continue
            eligible.append(lab)
        if len(eligible) < 2:
            continue
        eligible.sort(key=lambda lab: lab.laborer_id)
        rng = world.rng(f"pair:{town_id}:{now}")
        pool = list(eligible)
        while len(pool) >= 2:
            i = int(rng.random() * len(pool))
            a = pool.pop(i)
            j = int(rng.random() * len(pool))
            b = pool.pop(j)
            a.partner_id = b.laborer_id
            b.partner_id = a.laborer_id
            stats["paired"] += 1
            birth_rng = world.rng(f"birth:{a.laborer_id}:{now}")
            if birth_rng.random() >= BIRTH_CHANCE_PER_WEEK:
                continue
            _spawn_laborer_child(world, a, b, town_id)
            stats["born"] += 1
    return stats

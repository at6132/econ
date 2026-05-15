"""Phase 7B — laborer NPCs: the real population economy.

LaborerNPCs are mortal, needs-driven agents. They are NOT entrepreneurs:
they cannot claim plots, cannot operate businesses, cannot make capital
decisions. They work, they spend, they age, they die, and their migration
sends powerful demand signals across the four islands.

Money flow under Phase 7:

  entrepreneur → wages → laborer.cash → store → store owner (entrepreneur)
                                                       ↓
                                                  reinvestment

The bootstrap is the only injection: each laborer gets a $200 subsistence
stake at birth (real money in the ledger). After that, the only way
laborers acquire cash is wages from an employer; the only way they spend
it is through stores. Conservation must hold.

Phase 7B scope (this file):
- ``LaborerNPC`` dataclass + ledger account per laborer.
- ``seed_island_laborers`` bootstrap (deterministic per seed).
- ``tick_laborers`` lifecycle: need decay, health pressure, death,
  retirement, aging.
- ``tick_laborer_births`` per-town spawn loop.
- ``tick_laborer_migration`` minimal placeholder (full town-vs-town
  migration logic lands in 7C/7E once towns and jobs exist).

Phase 7D wires consumption into stores; Phase 7E wires wages and real
employment. This module defines the surface those phases plug into.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from realm.events.event_log import log_event
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import (
    AccountId,
    MoneyErr,
    party_cash_account,
    system_reserve_account,
)
from realm.world import World


# ───────────────────────────── tunables ─────────────────────────────


TICKS_PER_GAME_DAY: Final[int] = 1440
"""One game-day = 1,440 ticks (matches the rest of the simulation)."""

RETIREMENT_AGE_GAME_DAYS: Final[int] = 100
RETIREMENT_AGE_TICKS: Final[int] = RETIREMENT_AGE_GAME_DAYS * TICKS_PER_GAME_DAY

LABORER_STARTING_CASH_CENTS: Final[int] = 20_000
"""$200 subsistence stake. The only money injection on the laborer side."""

# Per game-day decay rates (units = need fraction lost per day).
FOOD_DECAY_PER_DAY: Final[float] = 0.05
FUEL_DECAY_PER_DAY: Final[float] = 0.03
SHELTER_DECAY_PER_DAY: Final[float] = 0.01

# Need thresholds: below these, the corresponding health pressure kicks in.
FOOD_LOW_THRESHOLD: Final[float] = 0.30
FUEL_LOW_THRESHOLD: Final[float] = 0.20
SHELTER_LOW_THRESHOLD: Final[float] = 0.50

# Per-day health decay when needs are critical.
FOOD_HEALTH_DECAY_PER_DAY: Final[float] = 0.02
FUEL_HEALTH_DECAY_PER_DAY: Final[float] = 0.01
SHELTER_HEALTH_DECAY_PER_DAY: Final[float] = 0.005

# Health bands.
PRODUCTIVITY_REDUCED_THRESHOLD: Final[float] = 0.30
"""Below 0.30 health → 30% productivity (sick worker)."""

DEATH_THRESHOLD: Final[float] = 0.10
"""At or below 0.10 health → laborer dies (logged as a world_feed event)."""

# Legacy four-island flavor table (pre–landmass-density). Tests that pin the
# old layout may still import this; bootstrap uses :mod:`landmass_density`.
DEFAULT_ISLAND_LABORER_COUNTS: Final[dict[int, int]] = {
    0: 300,
    1: 400,
    2: 150,
    3: 100,
}

# Birth control (Phase 7C/7D will revisit once towns exist).
BIRTH_CHECK_INTERVAL_GAME_DAYS: Final[int] = 7
BIRTH_TOWN_HEALTH_THRESHOLD: Final[float] = 0.60


__all__ = [
    "LaborerNPC",
    "TICKS_PER_GAME_DAY",
    "RETIREMENT_AGE_GAME_DAYS",
    "RETIREMENT_AGE_TICKS",
    "LABORER_STARTING_CASH_CENTS",
    "FOOD_DECAY_PER_DAY",
    "FUEL_DECAY_PER_DAY",
    "SHELTER_DECAY_PER_DAY",
    "FOOD_LOW_THRESHOLD",
    "FUEL_LOW_THRESHOLD",
    "SHELTER_LOW_THRESHOLD",
    "FOOD_HEALTH_DECAY_PER_DAY",
    "FUEL_HEALTH_DECAY_PER_DAY",
    "SHELTER_HEALTH_DECAY_PER_DAY",
    "PRODUCTIVITY_REDUCED_THRESHOLD",
    "DEATH_THRESHOLD",
    "DEFAULT_ISLAND_LABORER_COUNTS",
    "laborer_cash_account",
    "seed_island_laborers",
    "tick_laborers",
    "tick_laborer_births",
    "laborer_count_for_island",
    "unemployed_laborer_count_for_island",
    "productivity_multiplier",
]


# ───────────────────────────── dataclass ─────────────────────────────


@dataclass
class LaborerNPC:
    """A mortal, needs-driven NPC. Lives in a town, works for an entrepreneur."""

    laborer_id: str
    display_name: str
    island_id: int
    home_plot_id: PlotId
    home_town: str | None = None
    employer: PartyId | None = None
    skill_level: int = 0
    age_ticks: int = 0
    health: float = 1.0
    cash_cents: int = 0
    needs: dict[str, float] = field(
        default_factory=lambda: {"food": 1.0, "fuel": 1.0, "shelter": 1.0}
    )
    employment_contract: str | None = None
    """When set, wages follow the linked :class:`JobOpening`. Direct hires leave
    this ``None`` and use ``wage_per_day_cents`` instead."""
    wage_per_day_cents: int = 0
    """Daily wage for direct hires (no ``JobOpening``). Ignored when zero and an
    opening is linked — then the opening's wage applies."""
    migrating_to: str | None = None
    migration_arrives_tick: int = 0
    last_needs_tick: int = 0
    """Last simulation tick at which need-decay was applied — used to keep
    decay deterministic regardless of how often ``tick_laborers`` is called."""


# ───────────────────────────── accounts ─────────────────────────────


def laborer_cash_account(laborer_id: str) -> AccountId:
    """Ledger account holding this laborer's cash.

    Laborers are NOT in ``world.parties`` (they don't participate in
    actions, contracts, or order books directly). They have their own
    ``cash:lab:<laborer_id>`` account so wage/spend transfers are real
    ledger movements and conservation holds exactly.
    """
    return AccountId(f"cash:lab:{laborer_id}")


def town_treasury_account(town_id: str) -> AccountId:
    """Phase 9G — per-town treasury for sweeping orphan cash.

    When a laborer dies or retires their remaining cash flows to the
    town treasury instead of evaporating to system:reserve. This keeps
    spending power circulating inside the town (eventually Phase 11+
    will spend the treasury on civic maintenance / new residences).
    """
    return AccountId(f"cash:town:{town_id}")


def _ensure_laborer_cash_invariant(world: World, lab: LaborerNPC) -> None:
    """Re-sync the dataclass mirror to the ledger balance.

    The ledger is the source of truth. ``lab.cash_cents`` is a cached
    mirror updated by every transfer for fast reads — this helper exists
    for tests and snapshot-load paths.
    """
    lab.cash_cents = world.ledger.balance(laborer_cash_account(lab.laborer_id))


# ───────────────────────────── bootstrap ─────────────────────────────


def seed_island_laborers(world: World, island_id: int, count: int) -> list[str]:
    """Spawn ``count`` laborers on ``island_id``, distributed across land plots.

    Each laborer receives a real ledger account funded with
    ``LABORER_STARTING_CASH_CENTS`` from the system reserve — this is the
    one-and-only injection for laborer cash. Returns the list of newly
    created ``laborer_id``s in deterministic seed order.
    """
    plot_islands = world.scenario_state.get("plot_islands") or {}
    if not plot_islands:
        return []
    from realm.production.recipe_sites import plot_allows_structure

    candidate_plots = sorted(
        pid_s
        for pid_s, isl in plot_islands.items()
        if int(isl) == int(island_id)
        and (p := world.plots.get(PlotId(pid_s))) is not None
        and plot_allows_structure(p)
    )
    if not candidate_plots:
        return []
    from realm.genesis.laborer_names import generate_laborer_name

    rng = world.rng(f"seed_laborers:{island_id}:{count}")
    seeded: list[str] = []
    next_seq = int(world.scenario_state.setdefault("next_laborer_seq", 1))
    for _ in range(count):
        home_plot = PlotId(rng.choice(candidate_plots))
        lid = f"lab_{next_seq:05d}"
        next_seq += 1
        name = generate_laborer_name(rng)
        # Phase 9I - stagger initial laborer ages across the working
        # lifetime so retirements spread out instead of all firing on
        # day RETIREMENT_AGE_GAME_DAYS. Without this, the population
        # cliff-collapsed at exactly day 100 during long integration
        # runs. Random offset = 0..(0.7 * RETIREMENT_AGE_TICKS) so the
        # youngest cohort still has 30% of their working life ahead.
        starting_age = rng.randint(0, int(RETIREMENT_AGE_TICKS * 0.7))
        lab = LaborerNPC(
            laborer_id=lid,
            display_name=name,
            island_id=int(island_id),
            home_plot_id=home_plot,
            last_needs_tick=int(world.tick),
            age_ticks=starting_age,
        )
        acct = laborer_cash_account(lid)
        world.ledger.ensure_account(acct)
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=LABORER_STARTING_CASH_CENTS,
        )
        if isinstance(tr, MoneyErr):
            # Out of reserve — skip this laborer rather than crash bootstrap.
            continue
        lab.cash_cents = LABORER_STARTING_CASH_CENTS
        world.laborers[lid] = lab
        seeded.append(lid)
    world.scenario_state["next_laborer_seq"] = next_seq
    return seeded


def bootstrap_island_laborer_populations(world: World) -> dict[int, int]:
    """Seed every landmass with a plot-count–scaled laborer population.

    Returns ``{landmass_id: laborers_seeded}`` for the caller to log.
    """
    plot_islands = world.scenario_state.get("plot_islands") or {}
    if not plot_islands:
        return {}
    from realm.population.landmass_density import laborer_target_count_for_landmass

    distinct_islands = sorted({int(isl) for isl in plot_islands.values()})
    out: dict[int, int] = {}
    for isl in distinct_islands:
        count = laborer_target_count_for_landmass(world, isl)
        if count <= 0:
            continue
        ids = seed_island_laborers(world, isl, count)
        out[isl] = len(ids)
    return out


# ───────────────────────────── tick ─────────────────────────────


def productivity_multiplier(lab: LaborerNPC) -> float:
    """Production-line throughput multiplier for this laborer.

    Healthy laborers contribute 1.0; sick laborers (``health < 0.30``)
    drop to 0.30. Used by 7E employment integration; defined here so
    tests can exercise it without dragging in the production module.
    """
    if lab.health < PRODUCTIVITY_REDUCED_THRESHOLD:
        return 0.30
    return 1.0


def _apply_needs_decay(
    lab: LaborerNPC, days_elapsed: float, *, fuel_decay_rate: float = FUEL_DECAY_PER_DAY
) -> None:
    """Decay the three needs proportional to days elapsed.

    ``fuel_decay_rate`` defaults to ``FUEL_DECAY_PER_DAY`` (the Phase 7
    constant) but the caller can pass a season-modulated rate per Phase 8.A3
    — winter fuel decay is ~2× the summer rate.
    """
    lab.needs["food"] = max(0.0, lab.needs.get("food", 1.0) - FOOD_DECAY_PER_DAY * days_elapsed)
    lab.needs["fuel"] = max(0.0, lab.needs.get("fuel", 1.0) - fuel_decay_rate * days_elapsed)
    lab.needs["shelter"] = max(
        0.0, lab.needs.get("shelter", 1.0) - SHELTER_DECAY_PER_DAY * days_elapsed
    )


def _apply_health_pressure(
    lab: LaborerNPC, days_elapsed: float, *, epidemic_mult: float = 1.0
) -> None:
    """Drop health when needs are below their critical thresholds.

    Phase 8C: ``epidemic_mult`` accelerates the decay (typically ×3.0)
    for laborers in towns with an active epidemic outbreak.
    """
    drop = 0.0
    if lab.needs.get("food", 1.0) < FOOD_LOW_THRESHOLD:
        drop += FOOD_HEALTH_DECAY_PER_DAY * days_elapsed
    if lab.needs.get("fuel", 1.0) < FUEL_LOW_THRESHOLD:
        drop += FUEL_HEALTH_DECAY_PER_DAY * days_elapsed
    if lab.needs.get("shelter", 1.0) < SHELTER_LOW_THRESHOLD:
        drop += SHELTER_HEALTH_DECAY_PER_DAY * days_elapsed
    # Phase 8C: epidemic adds a baseline health decay even when needs are
    # met (people get sick regardless of food and shelter), and accelerates
    # any existing decay. Tuned so a 0.6-severity epidemic strips ~0.06 hp
    # per day from a fully-supplied laborer over its 10-20 day window.
    if epidemic_mult > 1.0:
        drop = drop * epidemic_mult + 0.02 * days_elapsed * (epidemic_mult - 1.0)
    if drop > 0.0:
        lab.health = max(0.0, lab.health - drop)


def _clear_job_openings_for_laborer(world: World, laborer_id: str) -> None:
    """Free slots when a laborer leaves the workforce (death / retirement)."""
    for op in world.job_openings:
        if op.filled_by == laborer_id:
            op.filled_by = None


def _kill_laborer(world: World, lab: LaborerNPC, cause: str) -> None:
    """Remove a laborer from the simulation.

    Phase 9G — remaining cash is swept to the laborer's town treasury
    (``cash:town:<town_id>``) so spending power stays inside the local
    economy instead of evaporating to system:reserve. Laborers with no
    home_town still sink to system:reserve (true frontier orphan case).
    The death is recorded as a world_feed event.
    """
    acct = laborer_cash_account(lab.laborer_id)
    remaining = world.ledger.balance(acct)
    if remaining > 0:
        if lab.home_town:
            tre = town_treasury_account(lab.home_town)
            world.ledger.ensure_account(tre)
            world.ledger.transfer(
                debit=acct,
                credit=tre,
                amount_cents=remaining,
            )
        else:
            world.ledger.transfer(
                debit=acct,
                credit=system_reserve_account(),
                amount_cents=remaining,
            )
    _clear_job_openings_for_laborer(world, lab.laborer_id)
    world.laborers.pop(lab.laborer_id, None)
    log_event(
        world,
        "world_feed",
        f"A laborer ({lab.display_name}) on island {lab.island_id} {cause}.",
        laborer_id=lab.laborer_id,
        island_id=lab.island_id,
        cause=cause,
        age_ticks=lab.age_ticks,
    )


def _retire_laborer(world: World, lab: LaborerNPC) -> None:
    """Retired laborer leaves the workforce.

    Phase 9G — cash flows to the town treasury (same as death) so it
    stays inside the local economy rather than sinking to system:reserve.
    """
    acct = laborer_cash_account(lab.laborer_id)
    remaining = world.ledger.balance(acct)
    if remaining > 0:
        if lab.home_town:
            tre = town_treasury_account(lab.home_town)
            world.ledger.ensure_account(tre)
            world.ledger.transfer(
                debit=acct,
                credit=tre,
                amount_cents=remaining,
            )
        else:
            world.ledger.transfer(
                debit=acct,
                credit=system_reserve_account(),
                amount_cents=remaining,
            )
    _clear_job_openings_for_laborer(world, lab.laborer_id)
    world.laborers.pop(lab.laborer_id, None)
    log_event(
        world,
        "laborer_retired",
        f"{lab.display_name} retired after {lab.age_ticks // TICKS_PER_GAME_DAY} game-days.",
        laborer_id=lab.laborer_id,
        island_id=lab.island_id,
    )


def tick_laborers(world: World) -> dict[str, int]:
    """Per-tick laborer lifecycle pass.

    Decay, health pressure, death, retirement, and aging are recomputed
    on every game-day boundary (every 1,440 ticks) by comparing the
    laborer's ``last_needs_tick`` with the current ``world.tick``. This
    keeps the pass cheap (most calls are no-ops) and idempotent under
    repeated invocation within the same day.

    Returns a small status dict useful for tests and digest writeups.

    Phase 8.A3: fuel-need decay is season-modulated — the rate is computed
    once per tick (same season for every laborer) and threaded into
    ``_apply_needs_decay``.
    """
    from realm.events.seasons import current_season, fuel_decay_per_day_for_season
    from realm.events.world_events import (
        active_epidemic_for_town,
        epidemic_health_decay_multiplier,
    )

    fuel_rate = fuel_decay_per_day_for_season(current_season(world))
    stats = {"died": 0, "retired": 0, "ticked": 0, "epidemic_deaths": 0}
    if not world.laborers:
        return stats
    now = int(world.tick)
    dead_ids: list[str] = []
    retired_ids: list[str] = []
    for lab in world.laborers.values():
        elapsed_ticks = now - int(lab.last_needs_tick)
        if elapsed_ticks <= 0:
            continue
        days_elapsed = elapsed_ticks / TICKS_PER_GAME_DAY
        _apply_needs_decay(lab, days_elapsed, fuel_decay_rate=fuel_rate)
        # Phase 8C: epidemic accelerates health decay in affected towns.
        epidemic_mult = epidemic_health_decay_multiplier(world, lab.home_town)
        _apply_health_pressure(lab, days_elapsed, epidemic_mult=epidemic_mult)
        lab.age_ticks += elapsed_ticks
        lab.last_needs_tick = now
        stats["ticked"] += 1
        if lab.health <= DEATH_THRESHOLD:
            dead_ids.append(lab.laborer_id)
        elif lab.age_ticks >= RETIREMENT_AGE_TICKS:
            retired_ids.append(lab.laborer_id)
    for lid in dead_ids:
        lab = world.laborers.get(lid)
        if lab is None:
            continue
        # Cause heuristic for the world_feed message.
        ep = active_epidemic_for_town(world, lab.home_town) if lab.home_town else None
        if ep is not None:
            cause = "died in the epidemic"
            ep.payload["deaths"] = int(ep.payload.get("deaths", 0)) + 1
            stats["epidemic_deaths"] += 1
        elif lab.needs.get("food", 1.0) < FOOD_LOW_THRESHOLD:
            cause = "died from hunger"
        elif lab.needs.get("fuel", 1.0) < FUEL_LOW_THRESHOLD:
            cause = "died from exposure"
        elif lab.needs.get("shelter", 1.0) < SHELTER_LOW_THRESHOLD:
            cause = "died from exposure"
        else:
            cause = "died"
        _kill_laborer(world, lab, cause)
        stats["died"] += 1
    for lid in retired_ids:
        lab = world.laborers.get(lid)
        if lab is None:
            continue
        _retire_laborer(world, lab)
        stats["retired"] += 1
    return stats


def tick_laborer_births(world: World) -> int:
    """Phase 7B placeholder — full birth logic lands in 7C alongside towns.

    Births require: a town with abundant food (a store with grain stock),
    residential capacity, and town health > 0.60. Towns don't exist yet
    in this sub-phase, so this function is wired but inert until 7C
    populates ``world.towns``. Returns the number of births that fired
    this tick (always 0 for now).
    """
    return 0


# ───────────────────────────── analytics ─────────────────────────────


def laborer_count_for_island(world: World, island_id: int) -> int:
    """Live laborer count on ``island_id`` — replaces the static density map."""
    return sum(1 for lab in world.laborers.values() if int(lab.island_id) == int(island_id))


def unemployed_laborer_count_for_island(world: World, island_id: int) -> int:
    """Unemployed laborer count — drives scarcity premiums in 7E."""
    return sum(
        1
        for lab in world.laborers.values()
        if int(lab.island_id) == int(island_id) and lab.employer is None
    )

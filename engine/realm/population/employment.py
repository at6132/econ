"""Phase 7E — employment market: real wages, real unemployment.

Laborers get hired by entrepreneurs through a job-posting → application
→ daily-wage flow. All cash movement is real ledger transfers between
the employer's cash account and the laborer's cash account (one per
laborer per ``realm.population.laborers.laborer_cash_account``). Conservation
holds: every cent paid in wages comes from some entrepreneur's account.

This complements the existing ``hire_worker_stub`` system (which models
abstract "worker bonuses" for production-line output) — it sits on top
of it, paying wages to *named* laborer NPCs each game-day. The two
systems can coexist: a settler can have a stub-hire bonus AND employ a
laborer with skills.

If the employer runs out of cash, the laborer quits and re-enters the
job market. Unemployed laborers burn through savings, can't afford
food, decline in health, and eventually migrate or die — turning
unemployment into a real economic pressure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from realm.events.event_log import log_event
from realm.core.ids import PartyId, PlotId
from realm.population.laborers import (
    TICKS_PER_GAME_DAY,
    laborer_cash_account,
)
from realm.core.ledger import MoneyErr, party_cash_account
from realm.world import World


# ───────────────────────────── tunables ─────────────────────────────


JOB_SEARCH_RADIUS_TILES: Final[int] = 5
"""How far an unemployed laborer can travel to apply to a job opening
that is *not* in their own town (Chebyshev distance from the laborer's
home plot)."""

DEFAULT_WAGE_PER_GAME_DAY_CENTS: Final[int] = 800
"""Baseline daily wage when an NPC employer posts a generic opening
(~$8/game-day - enough to cover the food + fuel basket and leave a small
surplus for savings/health buffer)."""

NPC_DAY1_OPENINGS_PER_EMPLOYER: Final[int] = 2
"""Each seeded entrepreneur NPC posts this many openings at bootstrap so
laborers have somewhere to go on day 1."""

NPC_DAY1_TARGET_EMPLOYMENT_RATIO: Final[float] = 0.30
"""Phase 7E aims to employ roughly this fraction of the bootstrap laborer
population on day 1 via NPC-posted openings. The remainder stays
unemployed and creates demand pressure for player-side hiring."""

MIN_WAGE_PER_GAME_DAY_CENTS: Final[int] = 100
"""Minimum legal daily wage ($1.00/day)."""

MAX_JOB_MATCHES_PER_DAY: Final[int] = 40
"""Cap hires per game-day so employment ramps gradually, not in one tick."""

JOB_OPENING_TTL_TICKS: Final[int] = 43_200
"""Drop unfilled openings older than 30 game-days."""

JOB_POSTING_CASH_THRESHOLD: Final[int] = 100_000
"""Settlers need $1,000 cash before posting wage jobs."""

PAYROLL_RESERVE_DAYS: Final[int] = 14
"""Employers must keep this many game-days of payroll in cash before opening a slot."""

JOB_WAGE_CENTS_PER_DAY: Final[int] = DEFAULT_WAGE_PER_GAME_DAY_CENTS


__all__ = [
    "JobOpening",
    "JOB_SEARCH_RADIUS_TILES",
    "DEFAULT_WAGE_PER_GAME_DAY_CENTS",
    "PAYROLL_RESERVE_DAYS",
    "post_job_opening",
    "cancel_job_opening",
    "tick_job_market",
    "tick_laborer_wages",
    "seed_genesis_npc_job_market",
    "job_openings_for_employer",
    "get_openings_for_party",
    "active_employment_count",
    "tick_settler_job_postings",
]


# ───────────────────────────── dataclass ─────────────────────────────


@dataclass
class JobOpening:
    """A live job opening on a specific plot, posted by an entrepreneur."""

    opening_id: str
    employer: PartyId
    plot_id: PlotId
    skill_min: int
    wage_per_day_cents: int
    posted_at_tick: int
    filled_by: str | None = None
    """When a laborer fills this opening, their ``laborer_id`` lands here.
    Filled openings remain in the list for snapshot/UI inspection until
    the laborer quits or is fired."""
    cpi_indexed: bool = False


# ───────────────────────────── owner actions ─────────────────────────────


def _employer_payroll_headcount(world: World, employer: PartyId) -> int:
    """Filled jobs + unfilled openings — the payroll the employer has committed to."""
    filled = sum(1 for lab in world.laborers.values() if lab.employer == employer)
    open_slots = sum(
        1
        for op in world.job_openings
        if op.employer == employer and op.filled_by is None
    )
    return filled + open_slots


def _employer_payroll_reserve_cents(
    world: World, employer: PartyId, *, extra_openings: int = 0
) -> int:
    """Cash buffer required to honor wages for ``PAYROLL_RESERVE_DAYS``."""
    headcount = _employer_payroll_headcount(world, employer) + int(extra_openings)
    return headcount * JOB_WAGE_CENTS_PER_DAY * PAYROLL_RESERVE_DAYS


def _employer_can_post_job(
    world: World, employer: PartyId, wage_per_day_cents: int
) -> bool:
    cash = world.ledger.balance(party_cash_account(employer))
    if cash < JOB_POSTING_CASH_THRESHOLD:
        return False
    reserve = _employer_payroll_reserve_cents(world, employer, extra_openings=1)
    reserve = max(reserve, wage_per_day_cents * PAYROLL_RESERVE_DAYS)
    return cash >= reserve


def post_job_opening(
    world: World,
    employer: PartyId,
    plot_id: PlotId,
    *,
    skill_min: int = 0,
    wage_per_day_cents: int = DEFAULT_WAGE_PER_GAME_DAY_CENTS,
    cpi_indexed: bool = False,
) -> dict:
    """Open a job slot on ``plot_id``. Returns the opening_id on success."""
    if employer not in world.parties:
        return {"ok": False, "reason": "unknown employer"}
    if skill_min < 0 or wage_per_day_cents < 0:
        return {"ok": False, "reason": "skill_min and wage must be non-negative"}
    if wage_per_day_cents < MIN_WAGE_PER_GAME_DAY_CENTS:
        return {"ok": False, "reason": "minimum wage is $1.00/day"}
    if not _employer_can_post_job(world, employer, wage_per_day_cents):
        return {"ok": False, "reason": "insufficient cash for payroll reserve"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != employer:
        return {"ok": False, "reason": "not your plot"}
    for op in world.job_openings:
        if op.employer == employer and op.plot_id == plot_id and op.filled_by is None:
            return {"ok": True, "opening_id": op.opening_id, "already_exists": True}
    next_seq = int(world.scenario_state.setdefault("next_job_opening_seq", 1))
    opening_id = f"job_{next_seq:06d}"
    world.scenario_state["next_job_opening_seq"] = next_seq + 1
    opening = JobOpening(
        opening_id=opening_id,
        employer=employer,
        plot_id=plot_id,
        skill_min=int(skill_min),
        wage_per_day_cents=int(wage_per_day_cents),
        posted_at_tick=int(world.tick),
        cpi_indexed=bool(cpi_indexed),
    )
    world.job_openings.append(opening)
    log_event(
        world,
        "job_posted",
        f"{employer} posted job at {plot_id} (skill>={skill_min}, ${wage_per_day_cents/100:.2f}/day)",
        opening_id=opening_id,
        employer=str(employer),
        plot_id=str(plot_id),
        skill_min=int(skill_min),
        wage_per_day_cents=int(wage_per_day_cents),
    )
    return {"ok": True, "opening_id": opening_id}


def cancel_job_opening(world: World, employer: PartyId, opening_id: str) -> dict:
    """Withdraw a job opening you posted. Filled openings are not cancellable
    here — fire the laborer first if you want to free the slot."""
    for i, op in enumerate(world.job_openings):
        if op.opening_id != opening_id:
            continue
        if op.employer != employer:
            return {"ok": False, "reason": "not your opening"}
        if op.filled_by is not None:
            return {"ok": False, "reason": "opening filled; fire the laborer first"}
        world.job_openings.pop(i)
        log_event(
            world,
            "job_cancelled",
            f"{employer} cancelled opening {opening_id}",
            opening_id=opening_id,
            employer=str(employer),
        )
        return {"ok": True}
    return {"ok": False, "reason": "unknown opening_id"}


# ───────────────────────────── tick: matching ─────────────────────────────


def _plot_island_id(world: World, plot_id: PlotId) -> int:
    raw = world.landmass_id.get(str(plot_id))
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    plot_islands = world.scenario_state.get("plot_islands") or {}
    try:
        return int(plot_islands.get(str(plot_id), -1))
    except (TypeError, ValueError):
        return -1


def _laborer_can_take(world: World, lab_id: str, opening: JobOpening) -> bool:
    """Skill + location gate for a laborer applying to an opening."""
    lab = world.laborers.get(lab_id)
    if lab is None or lab.employer is not None:
        return False
    if int(lab.skill_level) < int(opening.skill_min):
        return False
    plot = world.plots.get(opening.plot_id)
    if plot is None:
        return False
    job_island = _plot_island_id(world, opening.plot_id)
    if job_island >= 0 and int(lab.island_id) == job_island:
        return True
    home = world.plots.get(lab.home_plot_id)
    if home is None:
        return False
    if max(abs(plot.x - home.x), abs(plot.y - home.y)) > JOB_SEARCH_RADIUS_TILES:
        # Allow same-town matches regardless of tile distance — the
        # laborer is already commuting within the town's cluster.
        same_town = lab.home_town is not None and any(
            str(opening.plot_id) == str(rp)
            for t in world.towns.values()
            if t.town_id == lab.home_town
            for rp in (*t.residential_plots, *t.store_plots, t.center_plot)
        )
        if not same_town:
            return False
    return True


def _open_unfilled_openings(world: World) -> list[JobOpening]:
    return [op for op in world.job_openings if op.filled_by is None]


def _match_unfilled_openings(world: World, *, max_hires: int | None = None) -> int:
    """Deterministic matcher used by the daily tick and bootstrap seeding.

    Returns the number of laborers newly hired. When ``max_hires`` is set,
    stops after that many matches (daily tick); bootstrap passes ``None``.
    """
    openings = sorted(
        _open_unfilled_openings(world),
        key=lambda o: (-int(o.wage_per_day_cents), o.opening_id),
    )
    unemployed = sorted(
        [
            lid
            for lid, lab in world.laborers.items()
            if lab.employer is None
        ],
        key=lambda lid: (
            -int(world.laborers[lid].skill_level),
            lid,
        ),
    )
    hired = 0
    used: set[str] = set()
    for opening in openings:
        if max_hires is not None and hired >= max_hires:
            break
        match: str | None = None
        for lid in unemployed:
            if lid in used:
                continue
            if not _laborer_can_take(world, lid, opening):
                continue
            match = lid
            break
        if match is None:
            continue
        lab = world.laborers[match]
        lab.employer = opening.employer
        lab.employment_contract = opening.opening_id
        lab.wage_per_day_cents = int(opening.wage_per_day_cents)
        opening.filled_by = match
        used.add(match)
        hired += 1
        log_event(
            world,
            "laborer_hired",
            f"{lab.display_name} hired by {opening.employer} at {opening.plot_id} "
            f"(skill {lab.skill_level}, ${opening.wage_per_day_cents/100:.2f}/day)",
            opening_id=opening.opening_id,
            employer=str(opening.employer),
            laborer_id=match,
            plot_id=str(opening.plot_id),
            wage_per_day_cents=int(opening.wage_per_day_cents),
        )
    return hired


def _prune_stale_job_openings(world: World) -> None:
    cutoff = int(world.tick) - JOB_OPENING_TTL_TICKS
    kept: list[JobOpening] = []
    for op in world.job_openings:
        if op.filled_by is not None:
            kept.append(op)
            continue
        if int(op.posted_at_tick) >= cutoff:
            kept.append(op)
    world.job_openings = kept


def tick_job_market(world: World) -> dict[str, int]:
    """Match unemployed laborers to open positions, once per game-day.

    Matching policy (deterministic):

    1. Sort unfilled openings by (wage DESC, opening_id) so the highest-
       paying openings clear first.
    2. For each opening, pick the eligible unemployed laborer with the
       highest skill (tie-break by laborer_id) who can reach the
       opening's plot within ``JOB_SEARCH_RADIUS_TILES`` or whose home
       town owns the plot.
    3. Assign laborer.employer + filled_by + log a hire event.

    Returns ``{"hired": int, "openings_remaining": int}``.
    """
    out = {"hired": 0, "openings_remaining": 0}
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        # Job market clears once per game-day at the boundary.
        out["openings_remaining"] = len(_open_unfilled_openings(world))
        return out
    out["hired"] = _match_unfilled_openings(world, max_hires=MAX_JOB_MATCHES_PER_DAY)
    _prune_stale_job_openings(world)
    out["openings_remaining"] = sum(
        1 for o in world.job_openings if o.filled_by is None
    )
    return out


# ───────────────────────────── tick: wages ─────────────────────────────


def _opening_for_employment(world: World, contract_id: str) -> JobOpening | None:
    for op in world.job_openings:
        if op.opening_id == contract_id:
            return op
    return None


def tick_laborer_wages(world: World) -> dict[str, int]:
    """Pay one day of wages from every active employer to their laborers.

    Runs once per game-day. If the employer doesn't have enough cash to
    pay the wage, the laborer immediately quits and the opening reverts
    to unfilled — turning insolvency into a real labor-market signal.
    Returns ``{"paid": int, "quit_for_nonpayment": int, "cents_moved": int}``.
    """
    stats = {"paid": 0, "quit_for_nonpayment": 0, "cents_moved": 0}
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return stats
    for lid, lab in list(world.laborers.items()):
        if lab.employer is None:
            continue
        op = (
            _opening_for_employment(world, lab.employment_contract)
            if lab.employment_contract
            else None
        )
        if op is not None:
            wage = int(op.wage_per_day_cents)
            if bool(getattr(op, "cpi_indexed", False)):
                from realm.economy.cpi import cpi_multiplier

                wage = max(1, int(round(wage * float(cpi_multiplier(world)))))
        else:
            wpd = int(getattr(lab, "wage_per_day_cents", 0) or 0)
            wage = wpd if wpd > 0 else DEFAULT_WAGE_PER_GAME_DAY_CENTS
        if wage <= 0:
            stats["paid"] += 1
            continue
        emp_acct = party_cash_account(lab.employer)
        if world.ledger.balance(emp_acct) < wage:
            from realm.population.laborer_lifecycle import try_absorb_unpaid_wage_from_savings

            if try_absorb_unpaid_wage_from_savings(world, lab, int(wage)):
                stats["paid"] += 1
                continue
            # Employer insolvent for today's wage. Laborer quits.
            log_event(
                world,
                "wage_unpaid_quit",
                f"{lab.display_name} quit {lab.employer}: payroll empty",
                laborer_id=lid,
                employer=str(lab.employer),
                opening_id=lab.employment_contract or "",
            )
            if op is not None:
                op.filled_by = None
            lab.employer = None
            lab.employment_contract = None
            lab.wage_per_day_cents = 0
            stats["quit_for_nonpayment"] += 1
            continue
        lab_acct = laborer_cash_account(lid)
        world.ledger.ensure_account(lab_acct)
        tr = world.ledger.transfer(
            debit=emp_acct,
            credit=lab_acct,
            amount_cents=int(wage),
        )
        if isinstance(tr, MoneyErr):
            # Shouldn't happen after the balance check, but be defensive.
            continue
        lab.cash_cents = world.ledger.balance(lab_acct)
        from realm.population.laborer_lifecycle import apply_wage_savings_split

        apply_wage_savings_split(world, lab, int(wage))
        stats["paid"] += 1
        stats["cents_moved"] += int(wage)
    if stats["quit_for_nonpayment"] > 0:
        log_event(
            world,
            "world_feed",
            f"💼 {stats['quit_for_nonpayment']} laborers let go today — employers ran short on cash.",
            fired_count=int(stats["quit_for_nonpayment"]),
        )
    return stats


# ───────────────────────────── analytics ─────────────────────────────


def job_openings_for_employer(world: World, employer: PartyId) -> list[JobOpening]:
    return [op for op in world.job_openings if op.employer == employer]


def get_openings_for_party(world: World, party: PartyId) -> list[JobOpening]:
    """Unfilled openings posted by ``party`` (alias for API/tests)."""
    return [
        op
        for op in world.job_openings
        if op.employer == party and op.filled_by is None
    ]


_SKIP_JOB_BLUEPRINT_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"population", "infrastructure"}
)

_PRODUCTION_BUILDING_IDS: Final[frozenset[str]] = frozenset(
    {
        "strip_mine",
        "timber_yard",
        "grain_row",
        "power_shed",
        "wood_shop",
        "gristmill",
        "kiln_shed",
        "foundry",
        "stone_works",
        "assay_lab",
        "blast_furnace",
        "chemical_works",
        "forge_press",
        "machine_shop",
        "tool_workshop",
        "dock",
        "shipyard",
        "apothecary",
        "laboratory",
        "store",
    }
)


def _opening_exists_for_plot(
    world: World, employer: PartyId, plot_id: PlotId
) -> bool:
    for op in world.job_openings:
        if op.employer == employer and op.plot_id == plot_id and op.filled_by is None:
            return True
    return False


def _laborer_working_plot(world: World, employer: PartyId, plot_id: PlotId) -> bool:
    pid_s = str(plot_id)
    for lab in world.laborers.values():
        if lab.employer != employer:
            continue
        if lab.employment_contract:
            op = _opening_for_employment(world, lab.employment_contract)
            if op is not None and str(op.plot_id) == pid_s:
                return True
    return False


def maybe_post_job_openings_for_party(world: World, party: PartyId) -> int:
    """Post openings for each active production building without a filled slot."""
    if not _employer_can_post_job(world, party, JOB_WAGE_CENTS_PER_DAY):
        return 0

    posted = 0
    now = int(world.tick)
    seen_plots: set[str] = set()

    def _try_post(plot_key: str, blueprint_id: str) -> None:
        nonlocal posted
        if plot_key in seen_plots:
            return
        seen_plots.add(plot_key)
        if _opening_exists_for_plot(world, party, PlotId(plot_key)):
            return
        if _laborer_working_plot(world, party, PlotId(plot_key)):
            return
        bp = world.blueprints.get(blueprint_id)
        if bp is not None and bp.category in _SKIP_JOB_BLUEPRINT_CATEGORIES:
            return
        if blueprint_id == "road_segment":
            return
        if bp is None and blueprint_id not in _PRODUCTION_BUILDING_IDS:
            return
        res = post_job_opening(
            world,
            party,
            PlotId(plot_key),
            skill_min=0,
            wage_per_day_cents=JOB_WAGE_CENTS_PER_DAY,
        )
        if res.get("ok") and not res.get("already_exists"):
            posted += 1

    for pb in world.placed_buildings.values():
        if str(pb.built_by) != str(party):
            continue
        if str(pb.status) != "active":
            continue
        _try_post(str(pb.plot_id), str(pb.blueprint_id))

    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if int(row.get("completes_at_tick", 0)) > now:
            continue
        bid = str(row.get("building_id", ""))
        if not bid or bid == "residence":
            continue
        _try_post(str(row.get("plot_id", "")), bid)

    return posted


def tick_settler_job_postings(world: World) -> int:
    """Once per game-day: settlers post jobs for active workshops."""
    if world.scenario_id != "genesis":
        return 0
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return 0
    total = 0
    for party in sorted(
        (p for p in world.parties if str(p).startswith("settler_")), key=str
    ):
        total += maybe_post_job_openings_for_party(world, party)
    return total


def active_employment_count(world: World) -> int:
    return sum(1 for lab in world.laborers.values() if lab.employer is not None)


# ───────────────────────────── bootstrap ─────────────────────────────


def _eligible_npc_employers(world: World) -> list[PartyId]:
    """Pick all seeded entrepreneur-NPC parties with at least one owned plot."""
    out: list[PartyId] = []
    for p in sorted(world.parties, key=str):
        s = str(p)
        if s in (
            "player",
            "system",
            "genesis_settlement",
            "genesis_storekeeper",
            "genesis_exchange",
        ):
            continue
        # Has owned at least one land plot? Any party with a plot.owner set.
        for plot in world.plots.values():
            if plot.owner == p:
                out.append(p)
                break
    return out


def seed_genesis_npc_job_market(world: World) -> dict[str, int]:
    """Seed an opening on every NPC-owned plot at bootstrap.

    Aims to immediately employ roughly ``NPC_DAY1_TARGET_EMPLOYMENT_RATIO``
    of the laborer population so the consumer economy has wages flowing
    from day 1. Returns ``{"openings_posted": int, "hired_immediately": int}``.
    """
    out = {"openings_posted": 0, "hired_immediately": 0}
    if not world.laborers:
        return out
    employers = _eligible_npc_employers(world)
    if not employers:
        return out
    # Cap total openings at target employment ratio of laborers.
    target = max(
        1,
        int(len(world.laborers) * NPC_DAY1_TARGET_EMPLOYMENT_RATIO),
    )
    # Place at most one opening per NPC-owned plot, prioritising the
    # plots closest to each starting town center so laborers can reach
    # them within the radius gate.
    candidates: list[tuple[int, PartyId, PlotId]] = []
    for p in employers:
        for plot in world.plots.values():
            if plot.owner != p:
                continue
            # Distance to the nearest town center.
            best_d = 10_000
            for t in world.towns.values():
                center = world.plots.get(t.center_plot)
                if center is None:
                    continue
                d = max(abs(plot.x - center.x), abs(plot.y - center.y))
                if d < best_d:
                    best_d = d
            candidates.append((best_d, p, plot.plot_id))
    candidates.sort()
    posted = 0
    for _d, emp, pid in candidates:
        if posted >= target:
            break
        res = post_job_opening(
            world,
            emp,
            pid,
            skill_min=0,
            wage_per_day_cents=DEFAULT_WAGE_PER_GAME_DAY_CENTS,
        )
        if res.get("ok"):
            posted += 1
    out["openings_posted"] = posted
    # Run one synthetic round of matching immediately so day-1 laborers
    # start with employment. The bootstrap is the only place we bypass
    # the game-day gate; everything else flows through tick_job_market.
    out["hired_immediately"] = _match_unfilled_openings(world)
    return out

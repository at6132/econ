"""Regional labor markets (Sprint 3 — Phase C).

Each of the nine regions has a finite ``labor_pool`` — workers available for
hire there. Hiring decrements the pool; firing / contract end returns the
slot. Pools are seeded by :func:`bootstrap_labor_pools` at genesis bootstrap
based on the cached population density.

Scarcity feeds back into the economy through three channels:

1. ``hire_cost_multiplier_bps`` — when a region's pool is thin, the
   signing-bonus and recurring wage paid by ``hire_worker_stub`` is
   inflated by 1.25 × (thin) or 1.6 × (critical).
2. ``effective_output_bps_for_hire_status`` — buildings without any hired
   worker run at 50 % output; with workers they hit 100 %; with skilled
   workers they can climb to 120 %.
3. ``tick_labor_migration`` — once per game-day, a small share of the
   regional pool drifts toward whichever region offers the highest mean
   wage, making frontier wages "stickier" rather than instantly clearing.

Worker records live on ``world.stub_hires`` (one record per active hire).
Sprint 3 adds the following fields per record:

- ``region_id``: where the worker is based (filled in at hire time).
- ``skill_level``: int starting at 0; increments once per completed
  production cycle the worker participated in.
"""

from __future__ import annotations

from typing import Any, Final

from realm.ids import PartyId
from realm.regions import REGION_GRID_DIM, all_region_ids, region_for_coords
from realm.world import World


__all__ = [
    "REGION_LABOR_HUB_POOL",
    "REGION_LABOR_MID_POOL",
    "REGION_LABOR_FRONTIER_POOL",
    "LABOR_SCARCITY_THIN_THRESHOLD",
    "LABOR_SCARCITY_CRITICAL_THRESHOLD",
    "LABOR_SCARCITY_THIN_BPS",
    "LABOR_SCARCITY_CRITICAL_BPS",
    "LABOR_CRITICAL_HIRE_BATCH_SHARE_BPS",
    "WORKER_SKILL_BANDS",
    "LABOR_MIGRATION_DAILY_FRACTION_BPS",
    "LABOR_TRANSPORT_FEE_PER_WORKER_CENTS",
    "ensure_labor_state",
    "labor_market_active",
    "labor_pool_for_region",
    "bootstrap_labor_pools",
    "decrement_pool",
    "increment_pool",
    "hire_cost_multiplier_bps",
    "tick_labor_migration",
    "increment_worker_skill",
    "skill_bonus_bps",
    "effective_output_bps_for_run",
    "request_labor_transport",
    "tick_labor_transport_arrivals",
]


def labor_market_active(world: World) -> bool:
    """``True`` when the world has a bootstrapped regional labor market.

    Set by :func:`bootstrap_labor_pools`. Frontier and minimal test worlds
    leave this off so they keep the Sprint 1/2 hiring semantics (free
    workers, no understaffed output penalty).
    """
    state = world.scenario_state.get("labor")
    if not isinstance(state, dict):
        return False
    return bool(state.get("enabled"))


# ─────────────────── tunables ───────────────────


# Region buckets — used by ``bootstrap_labor_pools`` to seed the pool based on
# the population density of the region's centroid.
REGION_LABOR_HUB_POOL: Final[int] = 300
REGION_LABOR_MID_POOL: Final[int] = 110
REGION_LABOR_FRONTIER_POOL: Final[int] = 35

# Scarcity bands.
LABOR_SCARCITY_THIN_THRESHOLD: Final[int] = 50
LABOR_SCARCITY_CRITICAL_THRESHOLD: Final[int] = 20
LABOR_SCARCITY_THIN_BPS: Final[int] = 12_500  # 1.25 ×
LABOR_SCARCITY_CRITICAL_BPS: Final[int] = 16_000  # 1.60 ×
# Critical region: cap any single hire batch at 20 % of the remaining pool.
LABOR_CRITICAL_HIRE_BATCH_SHARE_BPS: Final[int] = 2_000

# Skill → output bonus (capped at +20 % so 120 % is the practical ceiling).
WORKER_SKILL_BANDS: Final[tuple[tuple[int, int], ...]] = (
    (5, 0),
    (15, 1_000),  # +10 %
    (30, 2_000),  # +20 %
    (10**9, 2_000),  # +20 % (capped per spec)
)

# Migration per game-day: up to 5 % of one region's slack drifts toward the
# highest-paying neighbour.
LABOR_MIGRATION_DAILY_FRACTION_BPS: Final[int] = 500  # 5 %

# Labor transport contract.
LABOR_TRANSPORT_FEE_PER_WORKER_CENTS: Final[int] = 500
LABOR_TRANSPORT_TICKS_PER_TILE: Final[int] = 2

_TICKS_PER_GAME_DAY: Final[int] = 1440


# ─────────────────── state ───────────────────


def ensure_labor_state(world: World) -> dict[str, Any]:
    """Lazy get-or-init the labor state in ``scenario_state``."""
    state = world.scenario_state.setdefault(
        "labor",
        {
            "pools": {},          # region_id → int
            "next_transport_id": 0,
            "transports": [],     # list of {id, employer, employee, src, dst, arrive_tick, qty}
        },
    )
    # Ensure pools dict exists for every region (defensive on save migration).
    pools: dict[str, int] = state.setdefault("pools", {})
    for r in all_region_ids():
        pools.setdefault(r, 0)
    return state


def labor_pool_for_region(world: World, region_id: str) -> int:
    state = ensure_labor_state(world)
    return int(state["pools"].get(region_id, 0))


def decrement_pool(world: World, region_id: str, qty: int = 1) -> bool:
    """Try to consume ``qty`` workers from the pool; returns ``True`` on success."""
    state = ensure_labor_state(world)
    cur = int(state["pools"].get(region_id, 0))
    if cur < qty:
        return False
    state["pools"][region_id] = cur - qty
    return True


def increment_pool(world: World, region_id: str, qty: int = 1) -> None:
    state = ensure_labor_state(world)
    state["pools"][region_id] = int(state["pools"].get(region_id, 0)) + int(qty)


# ─────────────────── bootstrap ───────────────────


def _region_centroid_density(world: World, region_id: str) -> float:
    """Mean population density across plots in this region (used to bucket pool size)."""
    density_map: dict[str, float] = world.scenario_state.get("population_density") or {}
    if not density_map:
        return 0.0
    if not world.plots:
        return 0.0
    max_x = max(p.x for p in world.plots.values()) + 1
    max_y = max(p.y for p in world.plots.values()) + 1
    total = 0.0
    n = 0
    for p in world.plots.values():
        r = region_for_coords(p.x, p.y, max_x, max_y)
        if r != region_id:
            continue
        d = density_map.get(str(p.plot_id))
        if d is None:
            continue
        total += float(d)
        n += 1
    return total / n if n else 0.0


def bootstrap_labor_pools(world: World) -> None:
    """Initialise pools based on per-region average population density.

    Hub-adjacent regions (mean density ≥ 0.40) get the hub pool size; mid
    regions (0.15–0.40) get the mid pool; frontier (< 0.15) gets the
    frontier pool. Also flips ``scenario_state["labor"]["enabled"]`` on
    so :func:`labor_market_active` returns ``True``.
    """
    state = ensure_labor_state(world)
    pools: dict[str, int] = state["pools"]
    for region_id in all_region_ids():
        if pools.get(region_id, 0) > 0:
            # Already seeded (e.g. snapshot reload).
            continue
        d = _region_centroid_density(world, region_id)
        if d >= 0.40:
            pools[region_id] = REGION_LABOR_HUB_POOL
        elif d >= 0.15:
            pools[region_id] = REGION_LABOR_MID_POOL
        else:
            pools[region_id] = REGION_LABOR_FRONTIER_POOL
    state["enabled"] = True


# ─────────────────── scarcity → cost / output ───────────────────


def _scarcity_class(pool: int) -> str:
    if pool <= LABOR_SCARCITY_CRITICAL_THRESHOLD:
        return "critical"
    if pool <= LABOR_SCARCITY_THIN_THRESHOLD:
        return "thin"
    return "abundant"


def hire_cost_multiplier_bps(world: World, region_id: str) -> int:
    """Multiplicative BPS for wages in this region (10000 = baseline)."""
    pool = labor_pool_for_region(world, region_id)
    klass = _scarcity_class(pool)
    if klass == "critical":
        return LABOR_SCARCITY_CRITICAL_BPS
    if klass == "thin":
        return LABOR_SCARCITY_THIN_BPS
    return 10_000


def critical_hire_batch_cap(world: World, region_id: str) -> int:
    """Max workers per single hire action when the regional pool is critical."""
    pool = labor_pool_for_region(world, region_id)
    klass = _scarcity_class(pool)
    if klass != "critical":
        return pool  # no cap
    return max(1, pool * LABOR_CRITICAL_HIRE_BATCH_SHARE_BPS // 10_000)


# ─────────────────── worker skill ───────────────────


def skill_bonus_bps(skill_level: int) -> int:
    """Return the per-worker output bonus in basis points."""
    sl = int(skill_level)
    for cap, bps in WORKER_SKILL_BANDS:
        if sl <= cap:
            return int(bps)
    return 0


def increment_worker_skill(world: World, employer: PartyId, *, by: int = 1) -> None:
    """Every active hire of ``employer`` gains ``by`` skill levels.

    Called by :func:`realm.production.tick_production` on each completed run.
    """
    for h in world.stub_hires:
        if str(h.get("employer")) != str(employer):
            continue
        h["skill_level"] = int(h.get("skill_level", 0)) + int(by)


def _active_hires_for_employer(world: World, employer: PartyId) -> list[dict[str, Any]]:
    return [h for h in world.stub_hires if str(h.get("employer")) == str(employer)]


def effective_output_bps_for_run(world: World, employer: PartyId, *, has_recipe_labor: bool) -> int:
    """Multiplicative BPS to apply to the recipe's outputs.

    - No active hires for an employer running a labour-bearing recipe → 5 000
      (50 % output, understaffed penalty).
    - Active hires: 10 000 + mean skill bonus, capped at 12 000 (120 %).

    Returns 10 000 (no modifier) when the labor market is inactive — Frontier
    and minimal-testbed worlds preserve the Sprint 1/2 behaviour.
    """
    if not has_recipe_labor:
        return 10_000
    if not labor_market_active(world):
        return 10_000
    hires = _active_hires_for_employer(world, employer)
    if not hires:
        return 5_000
    total = 0
    for h in hires:
        total += skill_bonus_bps(int(h.get("skill_level", 0)))
    mean_bonus = total // len(hires)
    return min(12_000, 10_000 + mean_bonus)


# ─────────────────── migration ───────────────────


def _region_mean_wage_cents(world: World, region_id: str) -> int:
    """Mean ``wage_per_tick_cents`` of active hires whose region is ``region_id``."""
    total = 0
    n = 0
    for h in world.stub_hires:
        if str(h.get("region_id") or "") != region_id:
            continue
        w = int(h.get("wage_per_tick_cents", 0))
        if w <= 0:
            continue
        total += w
        n += 1
    return total // n if n else 0


def tick_labor_migration(world: World) -> None:
    """Daily migration — workers move from low-wage to high-wage regions."""
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    state = ensure_labor_state(world)
    pools: dict[str, int] = state["pools"]
    regions = sorted(pools.keys())
    if len(regions) < 2:
        return
    # Single best-region target per day — keeps the move gentle.
    wages = {r: _region_mean_wage_cents(world, r) for r in regions}
    best_region = max(regions, key=lambda r: (wages[r], -pools.get(r, 0)))
    best_wage = wages[best_region]
    if best_wage <= 0:
        return
    moved_log: list[tuple[str, int]] = []
    for src in regions:
        if src == best_region:
            continue
        if wages[src] >= best_wage:
            continue
        cur = int(pools.get(src, 0))
        share = max(0, cur * LABOR_MIGRATION_DAILY_FRACTION_BPS // 10_000)
        if share <= 0:
            continue
        pools[src] = cur - share
        pools[best_region] = int(pools.get(best_region, 0)) + share
        moved_log.append((src, share))
    if moved_log:
        from realm.event_log import log_event

        log_event(
            world,
            "labor_migration",
            f"daily migration → {best_region}: "
            + ", ".join(f"{src}({share})" for src, share in moved_log),
            target_region=best_region,
            target_wage_cents=best_wage,
        )


# ─────────────────── labor transport ───────────────────


def request_labor_transport(
    world: World,
    *,
    employer: PartyId,
    employee: PartyId,
    src_region: str,
    dst_region: str,
    workers: int,
) -> dict[str, Any]:
    """Charge employer for transport and schedule workers to arrive in ``dst_region``."""
    from realm.ledger import MoneyErr, party_cash_account, system_reserve_account

    if workers <= 0:
        return {"ok": False, "reason": "workers must be positive"}
    if src_region not in all_region_ids() or dst_region not in all_region_ids():
        return {"ok": False, "reason": "unknown region"}
    if src_region == dst_region:
        return {"ok": False, "reason": "src and dst regions must differ"}
    if not decrement_pool(world, src_region, workers):
        return {"ok": False, "reason": "insufficient labor pool at source"}
    fee = workers * LABOR_TRANSPORT_FEE_PER_WORKER_CENTS
    cash = party_cash_account(employer)
    world.ledger.ensure_account(cash)
    if world.ledger.balance(cash) < fee:
        increment_pool(world, src_region, workers)  # refund pool
        return {"ok": False, "reason": "insufficient cash for transport"}
    tr = world.ledger.transfer(
        debit=cash, credit=system_reserve_account(), amount_cents=fee
    )
    if isinstance(tr, MoneyErr):
        increment_pool(world, src_region, workers)
        return {"ok": False, "reason": tr.reason}
    # Manhattan distance between region centroids in *region* coordinates ⇒
    # never exceeds 4 in a 3 × 3 grid; multiply by 2 ticks per spec.
    sx, sy = int(src_region.split("-")[1]), int(src_region.split("-")[2])
    dx, dy = int(dst_region.split("-")[1]), int(dst_region.split("-")[2])
    region_dist = abs(sx - dx) + abs(sy - dy)
    arrive_tick = int(world.tick) + max(1, region_dist * LABOR_TRANSPORT_TICKS_PER_TILE)
    state = ensure_labor_state(world)
    state["next_transport_id"] = int(state.get("next_transport_id", 0)) + 1
    transport_id = f"lt-{int(state['next_transport_id'])}"
    state.setdefault("transports", []).append(
        {
            "id": transport_id,
            "employer": str(employer),
            "employee": str(employee),
            "src_region": src_region,
            "dst_region": dst_region,
            "workers": int(workers),
            "fee_cents": int(fee),
            "arrive_tick": int(arrive_tick),
        }
    )
    from realm.event_log import log_event

    log_event(
        world,
        "labor_transport_dispatch",
        f"{employer} dispatched {workers} workers {src_region} → {dst_region} (arrive {arrive_tick})",
        employer=str(employer),
        src_region=src_region,
        dst_region=dst_region,
        workers=int(workers),
        fee_cents=int(fee),
        arrive_tick=int(arrive_tick),
        transport_id=transport_id,
    )
    return {
        "ok": True,
        "transport_id": transport_id,
        "fee_cents": int(fee),
        "arrive_tick": int(arrive_tick),
    }


def tick_labor_transport_arrivals(world: World) -> None:
    state = ensure_labor_state(world)
    transports = state.get("transports") or []
    remaining: list[dict[str, Any]] = []
    arrived: list[dict[str, Any]] = []
    for t in transports:
        if int(t.get("arrive_tick", 0)) <= int(world.tick):
            arrived.append(t)
        else:
            remaining.append(t)
    if arrived:
        from realm.event_log import log_event

        for t in arrived:
            increment_pool(world, str(t["dst_region"]), int(t["workers"]))
            log_event(
                world,
                "labor_transport_arrive",
                f"{t['workers']} workers arrived in {t['dst_region']} (transport {t['id']})",
                dst_region=str(t["dst_region"]),
                workers=int(t["workers"]),
                transport_id=str(t["id"]),
            )
    state["transports"] = remaining


def region_for_party_home(world: World, party: PartyId) -> str | None:
    """Best-effort: derive the region of a party's first-owned plot."""
    if not world.plots:
        return None
    max_x = max(p.x for p in world.plots.values()) + 1
    max_y = max(p.y for p in world.plots.values()) + 1
    for p in world.plots.values():
        if str(p.owner or "") == str(party):
            return region_for_coords(p.x, p.y, max_x, max_y)
    return None

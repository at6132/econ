"""Building condition decay and maintenance (Law 5 — decay without upkeep).

Each plot building has ``condition_bps`` in 0..10_000. Below ``BUILDING_MIN_EFFECTIVE_BPS`` the
structure no longer grants labor or storage bonuses until maintained.

Maintenance spends cash (fraction of original build cost) and restores condition to full.
"""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId, PlotId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World

BUILDING_CONDITION_FULL_BPS = 10_000
BUILDING_MIN_EFFECTIVE_BPS = 2_500
DECAY_BPS_PER_TICK = 14
MAINTENANCE_COST_DIVISOR = 5  # fee = max(1_000, build_cost_cents // 5)


def building_condition_bps(row: dict) -> int:
    v = row.get("condition_bps", BUILDING_CONDITION_FULL_BPS)
    try:
        n = int(v)
    except (TypeError, ValueError):
        return BUILDING_CONDITION_FULL_BPS
    return max(0, min(BUILDING_CONDITION_FULL_BPS, n))


def building_effective_for_bonuses(row: dict) -> bool:
    return building_condition_bps(row) >= BUILDING_MIN_EFFECTIVE_BPS


def tick_building_decay(world: World) -> None:
    """Apply passive decay to every structure each tick."""
    for b in world.plot_buildings:
        cur = building_condition_bps(b)
        bid = str(b.get("building_id", ""))
        rate = DECAY_BPS_PER_TICK
        if bid == "watch_hut":
            rate = max(1, DECAY_BPS_PER_TICK * 2 // 3)
        elif bid == "field_stockade":
            rate = max(1, DECAY_BPS_PER_TICK * 3 // 4)
        b["condition_bps"] = max(0, cur - rate)


def maintain_building(world: World, party: PartyId, instance_id: str) -> dict:
    """Pay maintenance; restore ``condition_bps`` to full for one building instance."""
    row: dict | None = None
    for b in world.plot_buildings:
        if str(b.get("instance_id", "")) == instance_id:
            row = b
            break
    if row is None:
        return {"ok": False, "reason": "unknown building instance"}
    if row.get("party") != str(party):
        return {"ok": False, "reason": "not your building"}
    plot_id = PlotId(str(row["plot_id"]))
    plot = world.plots.get(plot_id)
    if plot is None or plot.owner != party:
        return {"ok": False, "reason": "plot not owned"}
    base_cost = int(row.get("cost_cents", 25_000))
    fee = max(1_000, base_cost // MAINTENANCE_COST_DIVISOR)
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < fee:
        return {"ok": False, "reason": "insufficient cash for maintenance"}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=fee,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    row["condition_bps"] = BUILDING_CONDITION_FULL_BPS
    log_event(
        world,
        "maintain",
        f"{party} maintained {row.get('building_id')} on {plot_id} for ${fee / 100:.2f}",
        party=str(party),
        plot_id=str(plot_id),
        instance_id=instance_id,
        fee_cents=fee,
    )
    return {"ok": True, "fee_cents": fee}

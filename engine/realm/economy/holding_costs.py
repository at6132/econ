"""Daily inventory demurrage for parties without warehouse capacity."""

from __future__ import annotations

from realm.core.inventory import _normalize_bucket
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.player_economy import (
    FREE_STORAGE_UNITS_PER_PARTY,
    HOLDING_COST_CENTS_PER_UNIT_DAY,
    HOLDING_COST_INTERVAL_TICKS,
)
from realm.events.event_log import log_event
from realm.world import World

_EXEMPT_PREFIXES: frozenset[str] = frozenset({"genesis_", "system_", "frontier_"})


def _parties_with_warehouse(world: World) -> set[str]:
    """Parties that own at least one active warehouse building."""
    parties: set[str] = set()
    for pb in world.placed_buildings.values():
        if pb.blueprint_id == "warehouse" and pb.status == "active":
            parties.add(str(pb.built_by))
    for row in world.plot_buildings:
        if str(row.get("building_id")) == "warehouse":
            if int(row.get("completes_at_tick", 0) or 0) <= int(world.tick):
                parties.add(str(row.get("party", "")))
    return {p for p in parties if p}


def tick_holding_costs(world: World) -> None:
    """Daily demurrage: charge parties for excess inventory (money → system reserve)."""
    if int(world.tick) % HOLDING_COST_INTERVAL_TICKS != 0:
        return
    warehouse_parties = _parties_with_warehouse(world)
    inv_snapshot = world.inventory.snapshot()
    for party, materials in inv_snapshot.items():
        p_str = str(party)
        if any(p_str.startswith(pfx) for pfx in _EXEMPT_PREFIXES):
            continue
        if p_str in warehouse_parties:
            continue
        total_holding_cost = 0
        for _mat, raw in materials.items():
            qty = sum(_normalize_bucket(raw).values())
            excess = max(0, int(qty) - FREE_STORAGE_UNITS_PER_PARTY)
            total_holding_cost += excess * HOLDING_COST_CENTS_PER_UNIT_DAY
        if total_holding_cost <= 0:
            continue
        cash_acct = party_cash_account(party)
        bal = world.ledger.balance(cash_acct)
        actual = min(total_holding_cost, bal)
        if actual <= 0:
            continue
        world.ledger.transfer(
            debit=cash_acct,
            credit=system_reserve_account(),
            amount_cents=actual,
        )
        if actual >= 100:
            log_event(
                world,
                "holding_cost_charged",
                (
                    f"{party} paid {actual}¢ storage demurrage "
                    f"(holding >{FREE_STORAGE_UNITS_PER_PARTY} units without a warehouse)"
                ),
                party=p_str,
                holding_cost_cents=actual,
            )

"""Phase 8 — Sub-phase 8D: market cycles and structural economic events.

The natural-disaster system (8B) generates supply shocks; this module
generates *demand* and *credit* shocks plus structural state changes
that drive boom-bust cycles.

Public surface
--------------
* ``tick_market_panic_check(world)``     — spot a price spike and trigger NPC selling.
* ``tick_credit_crunch_check(world)``    — gate first_bank lending when overextended.
* ``trigger_boom_event(world, island, material)`` — spawn entrepreneur migration.
* ``tick_route_blockage_check(world)``   — close inter-island routes during severe storms.
* ``trigger_route_blockage(world, route_key, duration_days)`` — manual trigger.

Hooks:
* ``apply_bank_loan`` already reads ``world.scenario_state["bank_credit_crunch"]``.
* ``movement.dispatch_shipment`` reads ``world.scenario_state["blocked_routes"]``
  (set of route_key strings) before accepting new shipments.

Determinism: all probability rolls use ``world.rng(world.tick, "purpose")``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event

if TYPE_CHECKING:  # pragma: no cover
    from realm.world.world import World


# ─────────────────────────────────────────────────────────────────────────
# Tunables
# ─────────────────────────────────────────────────────────────────────────


PANIC_PRICE_SPIKE_BPS: int = 14_000  # 40% above 3-day moving average
PANIC_PROBABILITY: float = 0.4
PANIC_DUMP_OFFSET_CENTS: int = 5  # NPC sells 5c above current best bid
PANIC_DUMP_MIN_HOLDINGS: int = 10  # only NPCs with > 10 units take profit
PANIC_COOLDOWN_TICKS: int = TICKS_PER_GAME_DAY * 3

CREDIT_CRUNCH_HIGH_THRESHOLD_BPS: int = 6_500  # 65% utilisation triggers
CREDIT_CRUNCH_LOW_THRESHOLD_BPS: int = 5_000  # drop below 50% to lift

BOOM_PROBABILITY: float = 0.60
BOOM_NEW_NPC_COUNT_MIN: int = 3
BOOM_NEW_NPC_COUNT_MAX: int = 5
BOOM_NEW_NPC_SEED_CASH_CENTS: int = 1_500_000  # $15K per new entrepreneur

ROUTE_BLOCKAGE_PROBABILITY_FROM_STORM: float = 0.25
ROUTE_BLOCKAGE_MIN_DAYS: int = 5
ROUTE_BLOCKAGE_MAX_DAYS: int = 15


# ─────────────────────────────────────────────────────────────────────────
# Commodity price panic
# ─────────────────────────────────────────────────────────────────────────


def _three_day_moving_average(world: "World", material: str) -> int | None:
    """Mean best-ask over the trailing 3 game-days for ``material``.

    Returns ``None`` when there aren't enough samples yet.
    """
    window_ticks = TICKS_PER_GAME_DAY * 3
    floor_tick = int(world.tick) - window_ticks
    samples: list[int] = []
    for row in world.market_history:
        if int(row.get("tick", -1)) < floor_tick:
            continue
        asks = row.get("best_asks_cents") or {}
        v = asks.get(material)
        if v is not None and int(v) > 0:
            samples.append(int(v))
    if len(samples) < 3:
        return None
    return sum(samples) // len(samples)


def _current_best_ask(world: "World", material: str) -> int | None:
    lst = world.market_asks_by_material.get(material)
    if not lst:
        return None
    return min(int(o.price_per_unit_cents) for o in lst)


def _current_best_bid(world: "World", material: str) -> int | None:
    lst = world.market_bids_by_material.get(material)
    if not lst:
        return None
    return max(int(b.max_price_per_unit_cents) for b in lst)


def tick_market_panic_check(world: "World") -> None:
    """Detect a price spike on any material and trigger NPC panic selling.

    Spike condition: current best ask > 1.40 × 3-day moving average.
    On hit: every entrepreneur NPC holding > 10 units of that material
    places a sell order at ``best_bid + 5c`` (motivated seller). This dumps
    supply and crashes the price within 1-2 game-days.
    """
    if int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return
    cooldown_map = world.scenario_state.setdefault("market_panic_cooldown", {})
    for material in list(world.market_asks_by_material.keys()):
        last = int(cooldown_map.get(material, -10_000_000))
        if int(world.tick) - last < PANIC_COOLDOWN_TICKS:
            continue
        moving_avg = _three_day_moving_average(world, material)
        if moving_avg is None or moving_avg <= 0:
            continue
        current = _current_best_ask(world, material)
        if current is None:
            continue
        if current * 10_000 < moving_avg * PANIC_PRICE_SPIKE_BPS:
            continue
        rng = world.rng(f"panic-roll:{material}:t{world.tick}")
        if rng.random() >= PANIC_PROBABILITY:
            continue
        _trigger_panic_sell_off(world, material, moving_avg, current)
        cooldown_map[material] = int(world.tick)


def _trigger_panic_sell_off(
    world: "World",
    material: str,
    moving_avg: int,
    current_price: int,
) -> None:
    """Every NPC holding > threshold units of ``material`` places a sell."""
    from realm.economy.markets import place_sell_order

    bid = _current_best_bid(world, material) or max(1, current_price - 10)
    sell_price = max(1, int(bid) + PANIC_DUMP_OFFSET_CENTS)
    mid = MaterialId(material)
    sellers_engaged = 0
    units_dumped = 0
    for party in sorted(str(p) for p in world.parties):
        # Skip the player and the synthetic stand-ins (we want NPC entrepreneurs).
        if party in ("player",) or party.startswith("lab_"):
            continue
        holdings = int(world.inventory.qty(PartyId(party), mid))
        if holdings <= PANIC_DUMP_MIN_HOLDINGS:
            continue
        listing_qty = max(1, holdings // 4)  # dump 25% of stockpile
        res = place_sell_order(world, PartyId(party), mid, listing_qty, sell_price)
        if not res.get("ok"):
            continue
        sellers_engaged += 1
        units_dumped += listing_qty
    log_event(
        world,
        "world_feed",
        f"{material.replace('_', ' ').title()} prices surged sharply this week — "
        f"sellers responding with increased supply.",
        event_class="market_panic",
        material=material,
        moving_avg_cents=int(moving_avg),
        spike_price_cents=int(current_price),
        dump_price_cents=int(sell_price),
        sellers_engaged=int(sellers_engaged),
        units_dumped=int(units_dumped),
    )


# ─────────────────────────────────────────────────────────────────────────
# Credit crunch
# ─────────────────────────────────────────────────────────────────────────


def _bank_loan_outstanding_principal(world: "World") -> int:
    """Sum of active bank_loan principal_cents across all contracts."""
    from realm.genesis.bank import FIRST_BANK_PARTY_ID

    bank_id = str(FIRST_BANK_PARTY_ID)
    total = 0
    for c in world.contracts:
        if c.get("kind") != "bank_loan":
            continue
        if c.get("status") != "active":
            continue
        if str(c.get("lender", "")) != bank_id:
            continue
        total += int(c.get("principal_cents", 0))
    return total


def tick_credit_crunch_check(world: "World") -> None:
    """Toggle ``world.scenario_state["bank_credit_crunch"]`` based on bank loan book.

    Set TRUE when outstanding loans cross 65% of the bank's starting capital.
    Cleared once outstanding falls below 50%. Idempotent within a single tick.
    """
    from realm.genesis.bank import BANK_STARTING_CASH_CENTS

    capital = int(BANK_STARTING_CASH_CENTS)
    if capital <= 0:
        return
    outstanding = _bank_loan_outstanding_principal(world)
    util_bps = (outstanding * 10_000) // capital
    crunch = bool(world.scenario_state.get("bank_credit_crunch"))
    if not crunch and util_bps >= CREDIT_CRUNCH_HIGH_THRESHOLD_BPS:
        world.scenario_state["bank_credit_crunch"] = True
        log_event(
            world,
            "world_feed",
            "The First Bank of the Frontier has tightened lending standards. "
            "New loans suspended pending portfolio review.",
            event_class="credit_crunch_start",
            outstanding_cents=int(outstanding),
            utilisation_bps=int(util_bps),
        )
    elif crunch and util_bps <= CREDIT_CRUNCH_LOW_THRESHOLD_BPS:
        world.scenario_state["bank_credit_crunch"] = False
        log_event(
            world,
            "world_feed",
            "First Bank has resumed normal lending operations.",
            event_class="credit_crunch_end",
            outstanding_cents=int(outstanding),
            utilisation_bps=int(util_bps),
        )


# ─────────────────────────────────────────────────────────────────────────
# Boom town
# ─────────────────────────────────────────────────────────────────────────


def trigger_boom_event(
    world: "World",
    island_id: int,
    *,
    material: str = "iron_ore",
) -> dict:
    """Spawn ``BOOM_NEW_NPC_COUNT_MIN..MAX`` new entrepreneur NPCs on
    ``island_id``, each seeded with ``BOOM_NEW_NPC_SEED_CASH_CENTS``.

    Idempotent per (island, material) within a 30-day window — repeated
    triggers in close succession return the existing payload.
    """
    from realm.core.ledger import system_reserve_account
    from realm.core.ledger import MoneyErr

    key = f"boom:{island_id}:{material}"
    history = world.scenario_state.setdefault("boom_events", {})
    last = int(history.get(key, -10_000_000))
    if int(world.tick) - last < TICKS_PER_GAME_DAY * 30:
        return {"ok": False, "reason": "boom already active for this island/material"}
    rng = world.rng(f"boom-size:{key}:t{world.tick}")
    n_new = rng.randint(BOOM_NEW_NPC_COUNT_MIN, BOOM_NEW_NPC_COUNT_MAX)
    spawned: list[str] = []
    next_seq = int(world.scenario_state.get("next_boom_npc_seq", 1))
    for _ in range(n_new):
        pid = PartyId(f"boom_npc_{next_seq:05d}")
        next_seq += 1
        world.parties.add(pid)
        world.reputation[str(pid)] = {"honored": 0, "breached": 0}
        world.party_display_names[str(pid)] = (
            f"Prospector ({material.replace('_', ' ').title()} Boom)"
        )
        acct = party_cash_account(pid)
        world.ledger.ensure_account(acct)
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=BOOM_NEW_NPC_SEED_CASH_CENTS,
        )
        if isinstance(tr, MoneyErr):
            continue
        spawned.append(str(pid))
    world.scenario_state["next_boom_npc_seq"] = next_seq
    history[key] = int(world.tick)
    log_event(
        world,
        "world_feed",
        f"{material.replace('_', ' ').title()} discovery on island {island_id} is drawing settlers. "
        f"Population influx expected.",
        event_class="boom_event",
        island_id=int(island_id),
        material=material,
        new_npcs=len(spawned),
    )
    return {"ok": True, "spawned": spawned, "island_id": island_id, "material": material}


# ─────────────────────────────────────────────────────────────────────────
# Trade route blockage
# ─────────────────────────────────────────────────────────────────────────


def trigger_route_blockage(
    world: "World",
    route_key: str,
    *,
    duration_days: int | None = None,
) -> dict:
    """Close ``route_key`` (the canonical "region_a|region_b" string used by
    movement.py) for ``duration_days`` game-days. New shipments on this
    route refuse; in-transit shipments are unaffected (already at sea).
    """
    blocked = world.scenario_state.setdefault("blocked_routes", {})
    if duration_days is None:
        rng = world.rng(f"blockage-duration:{route_key}:t{world.tick}")
        duration_days = rng.randint(ROUTE_BLOCKAGE_MIN_DAYS, ROUTE_BLOCKAGE_MAX_DAYS)
    end_tick = int(world.tick) + duration_days * TICKS_PER_GAME_DAY
    blocked[route_key] = int(end_tick)
    log_event(
        world,
        "world_feed",
        f"The shipping lane {route_key} has been closed by severe weather. "
        f"Alternative routing required.",
        event_class="route_blockage_start",
        route_key=route_key,
        end_tick=int(end_tick),
        duration_days=int(duration_days),
    )
    return {"ok": True, "route_key": route_key, "end_tick": end_tick}


def is_route_blocked(world: "World", route_key: str) -> bool:
    """Read-only check used by ``movement.dispatch_shipment``."""
    blocked = world.scenario_state.get("blocked_routes") or {}
    end_tick = blocked.get(route_key)
    if end_tick is None:
        return False
    if int(world.tick) >= int(end_tick):
        # Lazy cleanup.
        try:
            del blocked[route_key]
            log_event(
                world,
                "world_feed",
                f"The {route_key} route has reopened. Normal shipping resumed.",
                event_class="route_blockage_end",
                route_key=route_key,
            )
        except KeyError:
            pass
        return False
    return True


def tick_route_blockage_expiry(world: "World") -> None:
    """Lazily expire blockages whose end_tick has passed (emits a feed line)."""
    blocked = world.scenario_state.get("blocked_routes") or {}
    to_drop: list[str] = []
    for rk, end_tick in list(blocked.items()):
        if int(world.tick) >= int(end_tick):
            to_drop.append(rk)
    for rk in to_drop:
        try:
            del blocked[rk]
        except KeyError:
            continue
        log_event(
            world,
            "world_feed",
            f"The {rk} route has reopened. Normal shipping resumed.",
            event_class="route_blockage_end",
            route_key=rk,
        )


def maybe_close_route_from_storm(world: "World", storm_event) -> None:
    """Storms with severity > 0.7 have a 25% chance of closing one
    inter-island route on the storm's island.

    Called by ``world_events.trigger_storm`` for severe storms.
    """
    if float(storm_event.severity) <= 0.7:
        return
    rng = world.rng(f"storm-route-roll:{storm_event.event_id}")
    if rng.random() >= ROUTE_BLOCKAGE_PROBABILITY_FROM_STORM:
        return
    isl = storm_event.island_id
    if isl is None:
        return
    # Pick the "default" route from this island to its closest neighbour.
    mapping = world.scenario_state.get("plot_islands") or {}
    other_islands = sorted({int(v) for v in mapping.values()} - {int(isl)})
    if not other_islands:
        return
    other = other_islands[0]
    # Region naming convention is approximate; use a simple deterministic key.
    a, b = sorted([int(isl), int(other)])
    route_key = f"island_{a}|island_{b}"
    trigger_route_blockage(world, route_key, duration_days=None)


# ─────────────────────────────────────────────────────────────────────────
# Main entry — called from advance_tick after market history is recorded
# ─────────────────────────────────────────────────────────────────────────


def tick_market_events(world: "World") -> None:
    """Phase 8D entry point: panic detection + credit crunch + blockage expiry."""
    if not bool(world.scenario_state.get("world_events_enabled", True)):
        tick_route_blockage_expiry(world)
        return
    tick_market_panic_check(world)
    tick_credit_crunch_check(world)
    tick_route_blockage_expiry(world)

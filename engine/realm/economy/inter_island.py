"""Phase 7F — Inter-island trade as a structural necessity.

The four-island Genesis world (Phase 7A) is intentionally tuned so that no
single island can satisfy its own laborer population. Phase 7F closes the
loop:

* Entrepreneur NPCs whose island runs a food deficit post real B2B **buy
  orders** for grain — driving inter-island arbitrage from surplus islands.
* The order book exposes the seller's island via
  :func:`market_book_for_island` so a player can filter to "show only Island B
  asks" and spot the cheap supply.
* Inter-island shipments already pay the 2× per-tile ocean modifier
  (:mod:`realm.infrastructure.movement`); this module never moves matter
  directly, it only signals demand via the existing order book.

No artificial demand: the buy orders cost the NPC their own cash and lock
that cash in market escrow exactly like a player order. Conservation holds.

This module is **Genesis-only**. On Frontier / single-continent scenarios
``plot_islands`` is empty and ``tick_inter_island_buy_orders`` is a no-op.
"""

from __future__ import annotations

from typing import Final

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.economy.markets import (
    best_resting_ask_cents,
    market_book_public,
    market_bids_public,
    place_buy_order,
)
from realm.events.event_log import log_event
from realm.world import World


__all__ = [
    "FOOD_GRAIN_PER_LABORER_PER_DAY",
    "MIN_FOOD_DEFICIT_TO_POST",
    "NPC_BUY_ORDER_COOLDOWN_TICKS",
    "NPC_BUY_ORDER_MAX_QTY",
    "NPC_BUY_PRICE_PREMIUM_BPS",
    "island_for_party",
    "food_supply_for_island",
    "food_demand_for_island",
    "food_deficit_for_island",
    "tick_inter_island_buy_orders",
    "market_book_for_island",
    "market_bids_for_island",
]


# ───────────────────────── tunables ─────────────────────────


FOOD_GRAIN_PER_LABORER_PER_DAY: Final[float] = 0.25
"""Rough grain-equivalent each laborer consumes per game-day. Food need
decays at 0.05/day; one grain restores 0.20 (Phase 7D). A laborer that buys
once every couple of days averages ~0.25 grain per day."""

MIN_FOOD_DEFICIT_TO_POST: Final[int] = 20
"""An island must run a grain-equivalent deficit ≥ this before the NPC
entrepreneur on the island posts an inter-island buy order."""

NPC_BUY_ORDER_COOLDOWN_TICKS: Final[int] = 1440
"""One buy order per island per game-day at most — keeps the book clean."""

NPC_BUY_ORDER_MAX_QTY: Final[int] = 40
"""Cap a single inter-island buy order — small enough to not corner the book."""

NPC_BUY_PRICE_PREMIUM_BPS: Final[int] = 1_500
"""Premium over current best ask for the NPC's bid (+15%) — a real buyer
pays up for cross-island delivery."""

_FOOD_BUY_MATERIAL: Final[MaterialId] = MaterialId("grain")


# ───────────────────────── party → island ─────────────────────────


def island_for_party(world: World, party: PartyId) -> int | None:
    """Which island ``party`` operates on (their first-owned plot).

    Returns ``None`` for parties without any plot (e.g. ``player`` before
    they claim, the genesis exchange, the bank, etc.).
    """
    islands_map = world.scenario_state.get("plot_islands") or {}
    if not islands_map:
        return None
    target = str(party)
    for plot_id_s, isl in islands_map.items():
        plot = world.plots.get(PlotId(plot_id_s))
        if plot is None or plot.owner is None:
            continue
        if str(plot.owner) == target:
            try:
                return int(isl)
            except (TypeError, ValueError):
                return None
    return None


# ───────────────────────── supply / demand ─────────────────────────


def _entrepreneurs_on_island(world: World, island_id: int) -> list[PartyId]:
    """Distinct party ids that own at least one plot on ``island_id``.

    Sorted by party id for determinism. Excludes the synthetic
    ``genesis_settlement`` and ``genesis_storekeeper`` placeholders so
    inter-island buy orders are placed by real entrepreneur NPCs.
    """
    islands_map = world.scenario_state.get("plot_islands") or {}
    # ``genesis_settlement`` is the synthetic placeholder behind seeded
    # residence buildings and ``genesis_exchange`` is the cold-start
    # clearinghouse — neither should be acting as a B2B buyer. The
    # storekeeper IS a valid buyer (Phase 7F funds them at bootstrap so
    # they can restock their store from cross-island grain).
    islands_map = world.scenario_state.get("plot_islands") or {}
    skip = {"genesis_settlement", "genesis_exchange"}
    out: set[str] = set()
    for plot_id_s, isl in islands_map.items():
        if int(isl) != int(island_id):
            continue
        plot = world.plots.get(PlotId(plot_id_s))
        if plot is None or plot.owner is None:
            continue
        owner_s = str(plot.owner)
        if owner_s in skip:
            continue
        out.add(owner_s)
    return [PartyId(p) for p in sorted(out)]


def food_supply_for_island(world: World, island_id: int) -> int:
    """Grain currently available to laborers on ``island_id``.

    Counts: store inventories whose store-plot sits on this island. The
    private inventory of entrepreneur NPCs isn't reachable by laborers
    directly (they only buy from stores), so it doesn't count as supply
    for this calculation.
    """
    islands_map = world.scenario_state.get("plot_islands") or {}
    total = 0
    for plot_id_s, inv in world.store_inventories.items():
        isl = islands_map.get(plot_id_s)
        if isl is None or int(isl) != int(island_id):
            continue
        total += int(inv.get(str(_FOOD_BUY_MATERIAL), 0))
        total += int(inv.get("bread", 0))
        total += int(inv.get("fish", 0))
    return total


def food_demand_for_island(world: World, island_id: int) -> int:
    """Expected grain consumption on ``island_id`` for the next day.

    Computed as: number of laborers on this island × per-day grain rate.
    Conservative (round up) so a tiny rounding error doesn't suppress
    a real deficit signal.
    """
    n_lab = sum(
        1 for lab in world.laborers.values() if int(lab.island_id) == int(island_id)
    )
    if n_lab <= 0:
        return 0
    # Round up so a fractional deficit always shows.
    return int(n_lab * FOOD_GRAIN_PER_LABORER_PER_DAY + 0.999)


def food_deficit_for_island(world: World, island_id: int) -> int:
    """Positive deficit when an island's supply can't cover its demand."""
    return max(0, food_demand_for_island(world, island_id) - food_supply_for_island(world, island_id))


# ───────────────────────── NPC buy-order tick ─────────────────────────


def _inter_island_state(world: World) -> dict:
    """Per-island scratch: ``{island_id: {"last_post_tick": int}}``."""
    return world.scenario_state.setdefault("inter_island", {"by_island": {}})


def _can_post_for_island(world: World, island_id: int) -> bool:
    """Cooldown gate — once per game-day per island."""
    state = _inter_island_state(world)
    last = int(
        state.get("by_island", {}).get(str(int(island_id)), {}).get("last_post_tick", -10**9)
    )
    return int(world.tick) - last >= NPC_BUY_ORDER_COOLDOWN_TICKS


def _mark_posted(world: World, island_id: int) -> None:
    state = _inter_island_state(world)
    state.setdefault("by_island", {}).setdefault(str(int(island_id)), {})[
        "last_post_tick"
    ] = int(world.tick)


def _pick_buyer_on_island(world: World, island_id: int) -> PartyId | None:
    """Pick the entrepreneur on this island with the most cash on hand.

    Most-cash bias keeps the buy order survivable (we lock cash in
    escrow). Deterministic tiebreak by party id.
    """
    candidates = _entrepreneurs_on_island(world, island_id)
    if not candidates:
        return None
    scored: list[tuple[int, str, PartyId]] = []
    for p in candidates:
        bal = int(world.ledger.balance(party_cash_account(p)))
        scored.append((-bal, str(p), p))
    scored.sort()
    return scored[0][2]


def tick_inter_island_buy_orders(world: World) -> dict[str, int]:
    """Once per game-day, post grain buy orders on food-deficit islands.

    For each island whose laborer demand outstrips on-island store stock by
    at least :data:`MIN_FOOD_DEFICIT_TO_POST` grain-equivalents, the
    cash-richest entrepreneur NPC on that island places a real B2B bid for
    grain at the current best ask + 15%. The bid sits on the standard
    market book — any seller (including settlers on a surplus island) can
    fill it, and the resulting fill is a cross-island ledger transfer.

    Returns ``{"posted": int, "deficit_islands": int}`` for tests / logs.
    """
    out = {"posted": 0, "deficit_islands": 0}
    plot_islands = world.scenario_state.get("plot_islands") or {}
    if not plot_islands:
        return out
    distinct_islands = sorted({int(isl) for isl in plot_islands.values()})
    for isl in distinct_islands:
        deficit = food_deficit_for_island(world, isl)
        if deficit < MIN_FOOD_DEFICIT_TO_POST:
            continue
        out["deficit_islands"] += 1
        if not _can_post_for_island(world, isl):
            continue
        buyer = _pick_buyer_on_island(world, isl)
        if buyer is None:
            continue
        best_ask = best_resting_ask_cents(world, _FOOD_BUY_MATERIAL)
        if best_ask is None:
            # No grain anywhere — bid at a sane premium over the typical
            # exchange ask so a Tier-1 producer is motivated to sell.
            from realm.economy.pricing import exchange_ask_cents

            base = int(exchange_ask_cents(_FOOD_BUY_MATERIAL))
        else:
            base = int(best_ask)
        bid_px = max(1, base * (10_000 + NPC_BUY_PRICE_PREMIUM_BPS) // 10_000)
        qty = min(NPC_BUY_ORDER_MAX_QTY, deficit)
        # Don't post a bid we can't fund.
        cash = int(world.ledger.balance(party_cash_account(buyer)))
        affordable = cash // bid_px if bid_px > 0 else 0
        qty = min(qty, int(affordable))
        if qty <= 0:
            continue
        res = place_buy_order(world, buyer, _FOOD_BUY_MATERIAL, qty, bid_px)
        if not res.get("ok"):
            continue
        _mark_posted(world, isl)
        out["posted"] += 1
        log_event(
            world,
            "inter_island_buy",
            f"{buyer} (island {isl}) posted cross-island bid for {qty}×grain "
            f"@ {bid_px}¢ (local deficit {deficit}).",
            buyer=str(buyer),
            island_id=int(isl),
            material=str(_FOOD_BUY_MATERIAL),
            qty=int(qty),
            price_per_unit_cents=int(bid_px),
            local_deficit=int(deficit),
        )
    return out


# ───────────────────────── region-filtered book ─────────────────────────


def _augment_with_island_id(world: World, rows: list[dict]) -> list[dict]:
    """Decorate ``market_book_public`` / ``market_bids_public`` rows with
    the seller's / bidder's island id (``None`` for parties off-map)."""
    cache: dict[str, int | None] = {}
    out: list[dict] = []
    for row in rows:
        pid = str(row.get("party"))
        if pid not in cache:
            cache[pid] = island_for_party(world, PartyId(pid))
        new_row = dict(row)
        new_row["island_id"] = cache[pid]
        out.append(new_row)
    return out


def market_book_for_island(
    world: World, *, island_id: int | None = None
) -> list[dict]:
    """Asks visible from the perspective of ``island_id``.

    ``island_id is None`` → unfiltered "all islands" view (with island_id
    annotations on every row). ``island_id`` set → only asks placed by
    parties operating on that island (other islands' asks would still
    require an inter-island shipment to consume).
    """
    rows = _augment_with_island_id(world, market_book_public(world))
    if island_id is None:
        return rows
    return [r for r in rows if r.get("island_id") == int(island_id)]


def market_bids_for_island(
    world: World, *, island_id: int | None = None
) -> list[dict]:
    """Bids visible from the perspective of ``island_id`` (mirror of
    :func:`market_book_for_island`)."""
    rows = _augment_with_island_id(world, market_bids_public(world))
    if island_id is None:
        return rows
    return [r for r in rows if r.get("island_id") == int(island_id)]

"""Per-settler cost-basis tracking (Sprint 2 — Phase B).

Settlers no longer anchor their ask price to the exchange's quote. Instead,
each settler maintains a running weighted-average of the cents they actually
paid for each input material (``input_avg_paid``) and, from that, computes a
per-output cost basis (``output_basis``) for everything they produce.

Their listing price becomes ``output_basis × (1 + target_margin_pct)``. A
settler who owns their own coal mine pays nothing for coal → coal contributes
0 to the iron-ingot basis → they can profitably undercut a settler who buys
coal from the exchange. Vertical integration has direct, measurable impact on
price competitiveness, exactly per the Sprint 2 spec.

State is stored under ``world.scenario_state["settler_cost_basis"]``:

    {
        "<party_id>": {
            "input_avg_paid": {"coal": 64, ...},  # cents/unit, weighted avg
            "input_qty_purchased": {"coal": 412, ...},  # cumulative qty
            "input_last_paid_tick": {"coal": 8640, ...},
            "input_price_history": {"coal": [...]},  # rolling [(tick, ¢/u), ...]
            "output_basis": {"iron_ingot": 280, ...},  # cents/unit (post-EMA)
            "output_qty_produced": {"iron_ingot": 38, ...},
        }
    }

JSON-safe; rounds through the existing snapshot path without a version bump.
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.recipes import RECIPES
from realm.world import World


__all__ = [
    "ensure_cost_basis_state",
    "record_settler_buy",
    "record_settler_production",
    "settler_input_avg_paid_cents",
    "settler_output_basis_cents",
    "settler_input_price_change_bps_7d",
    "SETTLER_LIST_MARGIN_BPS",
    "SETTLER_BUFFER_BUY_PRICE_RISE_BPS",
    "SETTLER_BUFFER_BUY_DAYS_FORWARD",
]


# ───────────────────────── tunables ─────────────────────────


SETTLER_LIST_MARGIN_BPS: int = 3_500
"""35% — settler ask = ``output_basis × 1.35``."""

SETTLER_OUTPUT_EMA_BPS: int = 6_000
"""60% weight on the latest production cycle's basis (vs prior accumulated EMA)."""

SETTLER_BUFFER_BUY_PRICE_RISE_BPS: int = 2_000
"""20% — buffer-buy trigger when the 7-day input price rises by this much."""

SETTLER_BUFFER_BUY_DAYS_FORWARD: int = 3
"""Buy this many game-days of forward consumption when buffering."""

_TICKS_PER_GAME_DAY: int = 1440
_PRICE_HISTORY_WINDOW_TICKS: int = 7 * _TICKS_PER_GAME_DAY
_PRICE_HISTORY_MAX_ENTRIES: int = 256


# ───────────────────────── state accessors ─────────────────────────


def ensure_cost_basis_state(world: World) -> dict[str, dict[str, Any]]:
    """Get-or-create the ``scenario_state["settler_cost_basis"]`` blob."""
    return world.scenario_state.setdefault("settler_cost_basis", {})


def _party_blob(world: World, party: PartyId) -> dict[str, Any]:
    root = ensure_cost_basis_state(world)
    blob = root.setdefault(str(party), {})
    blob.setdefault("input_avg_paid", {})
    blob.setdefault("input_qty_purchased", {})
    blob.setdefault("input_last_paid_tick", {})
    blob.setdefault("input_price_history", {})
    blob.setdefault("output_basis", {})
    blob.setdefault("output_qty_produced", {})
    return blob


# ───────────────────────── buy-side bookkeeping ─────────────────────────


def record_settler_buy(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    spent_cents: int,
) -> None:
    """Update the weighted-avg cents-per-unit for a settler's market_buy fill.

    Safe to call with ``qty=0`` (no-op). Always called *after* the buy has
    cleared so ``spent_cents`` reflects the executed price-time-priority walk.
    """
    if qty <= 0 or spent_cents <= 0:
        return
    if not str(party).startswith("settler_"):
        return
    blob = _party_blob(world, party)
    avg_map = blob["input_avg_paid"]
    qty_map = blob["input_qty_purchased"]
    tick_map = blob["input_last_paid_tick"]
    hist_map = blob["input_price_history"]

    key = str(material)
    prior_qty = int(qty_map.get(key, 0))
    prior_avg = int(avg_map.get(key, 0))
    new_qty = prior_qty + int(qty)
    # Cumulative VWAP. Integer math; round to nearest cent.
    new_total = prior_qty * prior_avg + int(spent_cents)
    new_avg = max(1, (new_total + new_qty // 2) // max(1, new_qty))
    avg_map[key] = new_avg
    qty_map[key] = new_qty
    tick_map[key] = int(world.tick)

    # Price history: append latest unit price and trim entries older than the window.
    unit_price = max(1, (int(spent_cents) + int(qty) - 1) // int(qty))
    history = hist_map.setdefault(key, [])
    history.append([int(world.tick), int(unit_price)])
    cutoff = int(world.tick) - _PRICE_HISTORY_WINDOW_TICKS
    while history and int(history[0][0]) < cutoff:
        history.pop(0)
    if len(history) > _PRICE_HISTORY_MAX_ENTRIES:
        del history[: len(history) - _PRICE_HISTORY_MAX_ENTRIES]


def settler_input_avg_paid_cents(
    world: World, party: PartyId, material: MaterialId
) -> int | None:
    root = world.scenario_state.get("settler_cost_basis") or {}
    blob = root.get(str(party)) or {}
    avg_map = blob.get("input_avg_paid") or {}
    val = avg_map.get(str(material))
    if val is None:
        return None
    return int(val)


def settler_input_price_change_bps_7d(
    world: World, party: PartyId, material: MaterialId
) -> int | None:
    """Return the BPS price change of ``material`` over the last 7 game-days.

    Positive = price went up. Returns ``None`` if the history is empty or has
    fewer than two distinct buys.
    """
    root = world.scenario_state.get("settler_cost_basis") or {}
    blob = root.get(str(party)) or {}
    hist_map = blob.get("input_price_history") or {}
    history = hist_map.get(str(material)) or []
    if len(history) < 2:
        return None
    cutoff = int(world.tick) - _PRICE_HISTORY_WINDOW_TICKS
    early = next(
        (int(p) for (t, p) in history if int(t) >= cutoff),
        int(history[0][1]),
    )
    latest = int(history[-1][1])
    if early <= 0:
        return None
    return int((latest - early) * 10_000 // early)


# ───────────────────────── production-side bookkeeping ─────────────────────────


def record_settler_production(
    world: World,
    party: PartyId,
    recipe_id: str,
    output_material: MaterialId,
    output_qty: int,
) -> None:
    """Update the per-output cost basis after a production cycle completes.

    Per-unit basis for this cycle =
    ``sum(input_qty × avg_paid(input)) / output_qty + labor_cents / output_qty``.

    Inputs the settler never bought (e.g. coal they extracted themselves) cost
    them ¢0 — that's how vertical integration mechanically lowers their basis.

    The recorded basis is an EMA toward this cycle, so single-cycle volatility
    doesn't whip the ask price around.
    """
    if output_qty <= 0:
        return
    if not str(party).startswith("settler_"):
        return
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return
    blob = _party_blob(world, party)
    avg_map = blob["input_avg_paid"]
    basis_map = blob["output_basis"]
    qty_map = blob["output_qty_produced"]

    input_cents = 0
    for inp, in_qty in recipe.inputs.items():
        paid = avg_map.get(str(inp))
        if paid is None:
            continue  # not bought — extracted by this settler, contributes 0
        input_cents += int(paid) * int(in_qty)
    labor_cents = int(getattr(recipe, "labor_cents", 0))
    cycle_basis = max(1, (input_cents + labor_cents + output_qty - 1) // output_qty)

    key = str(output_material)
    prior_basis = int(basis_map.get(key, 0))
    if prior_basis <= 0:
        new_basis = cycle_basis
    else:
        ema = SETTLER_OUTPUT_EMA_BPS
        new_basis = max(1, (cycle_basis * ema + prior_basis * (10_000 - ema) + 9_999) // 10_000)
    basis_map[key] = new_basis
    qty_map[key] = int(qty_map.get(key, 0)) + int(output_qty)


def settler_output_basis_cents(
    world: World, party: PartyId, material: MaterialId
) -> int | None:
    root = world.scenario_state.get("settler_cost_basis") or {}
    blob = root.get(str(party)) or {}
    basis_map = blob.get("output_basis") or {}
    val = basis_map.get(str(material))
    if val is None:
        return None
    return int(val)


def settler_listing_price_cents(
    world: World, party: PartyId, material: MaterialId
) -> int | None:
    """Return ``output_basis × (1 + SETTLER_LIST_MARGIN_BPS)``, or ``None``
    if the settler has no recorded basis for ``material``.
    """
    basis = settler_output_basis_cents(world, party, material)
    if basis is None:
        return None
    return max(4, (basis * (10_000 + SETTLER_LIST_MARGIN_BPS) + 9_999) // 10_000)

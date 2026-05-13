"""Analytics NPC vendor service (Sprint 4 — Phase B).

A single named NPC that sells purchasable intelligence as paid signals (never
prescriptions). Every product:

- Charges a fixed fee from the buyer to the vendor's cash account.
- Appends a record to ``world.analytics_purchases`` for UI display.
- Returns *signals* — significant / minor / shortage flags — not exact amounts.

Products
--------
1. ``price_history`` — last 30 game-days of best-ask history for a material.
2. ``regional_survey`` — averaged subsurface grade for a mineral across a region.
3. ``party_volume`` — categorical trade-volume profile for a target party.
4. ``supply_shortage`` — materials with < 10 ask-units for the past 3 game-days.

Law 6: information has cost. The vendor charges in cash, and the data they sell
is bounded — buyers see signals, not the full picture (information asymmetry
done right).
"""

from __future__ import annotations

import statistics
from typing import Any, Final

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.regions import _world_bounds, region_for_coords
from realm.world import World


__all__ = [
    "ANALYTICS_VENDOR_PARTY_ID",
    "ANALYTICS_VENDOR_DISPLAY_NAME",
    "PRICE_HISTORY_COST_CENTS",
    "REGIONAL_SURVEY_COST_CENTS",
    "PARTY_VOLUME_COST_CENTS",
    "SUPPLY_SHORTAGE_COST_CENTS",
    "SIGNIFICANT_VOLUME_THRESHOLD",
    "SHORTAGE_UNIT_THRESHOLD",
    "SHORTAGE_DAYS",
    "PARTY_VOLUME_WINDOW_DAYS",
    "PRICE_HISTORY_WINDOW_DAYS",
    "seed_analytics_vendor",
    "purchase_analytics_product",
]


ANALYTICS_VENDOR_PARTY_ID: Final[PartyId] = PartyId("analytics_vendor")
ANALYTICS_VENDOR_DISPLAY_NAME: Final[str] = "Frontier Analytics Bureau"
ANALYTICS_VENDOR_STARTING_CASH_CENTS: Final[int] = 1_000_000  # $10,000

# Product fees.
PRICE_HISTORY_COST_CENTS: Final[int] = 300
REGIONAL_SURVEY_COST_CENTS: Final[int] = 500
PARTY_VOLUME_COST_CENTS: Final[int] = 800
SUPPLY_SHORTAGE_COST_CENTS: Final[int] = 400

# Categorical thresholds.
SIGNIFICANT_VOLUME_THRESHOLD: Final[int] = 50
SHORTAGE_UNIT_THRESHOLD: Final[int] = 10
SHORTAGE_DAYS: Final[int] = 3
PARTY_VOLUME_WINDOW_DAYS: Final[int] = 7
PRICE_HISTORY_WINDOW_DAYS: Final[int] = 30
_TICKS_PER_GAME_DAY: Final[int] = 1440

_VALID_PRODUCTS: Final[frozenset[str]] = frozenset(
    {"price_history", "regional_survey", "party_volume", "supply_shortage"}
)

_PRODUCT_COSTS: Final[dict[str, int]] = {
    "price_history": PRICE_HISTORY_COST_CENTS,
    "regional_survey": REGIONAL_SURVEY_COST_CENTS,
    "party_volume": PARTY_VOLUME_COST_CENTS,
    "supply_shortage": SUPPLY_SHORTAGE_COST_CENTS,
}


def seed_analytics_vendor(
    world: World, *, starting_cash_cents: int | None = None
) -> bool:
    """Spawn the analytics vendor in Genesis worlds. Idempotent."""
    if world.scenario_id != "genesis":
        return False
    pid = ANALYTICS_VENDOR_PARTY_ID
    if pid in world.parties:
        return False
    cash = (
        starting_cash_cents
        if starting_cash_cents is not None
        else ANALYTICS_VENDOR_STARTING_CASH_CENTS
    )
    world.parties.add(pid)
    world.reputation[str(pid)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(pid)] = ANALYTICS_VENDOR_DISPLAY_NAME
    acct = party_cash_account(pid)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=cash,
    )
    if isinstance(tr, MoneyErr):
        return False
    log_event(
        world,
        "analytics_vendor_seeded",
        f"{ANALYTICS_VENDOR_DISPLAY_NAME} opened with ${cash // 100:,} reserves",
        party=str(pid),
    )
    return True


# ───────────────────────── product handlers ─────────────────────────


def _price_history_for_material(
    world: World, material: str, *, days: int = PRICE_HISTORY_WINDOW_DAYS
) -> list[dict[str, Any]]:
    """Best-ask snapshots from the past ``days`` game-days for ``material``."""
    window_ticks = days * _TICKS_PER_GAME_DAY
    cutoff = max(0, int(world.tick) - window_ticks)
    series: list[dict[str, Any]] = []
    for row in world.market_history:
        tick = int(row.get("tick", 0))
        if tick < cutoff:
            continue
        best_asks = row.get("best_asks_cents") or {}
        if not isinstance(best_asks, dict):
            continue
        if material not in best_asks:
            continue
        series.append({"tick": tick, "price_cents": int(best_asks[material])})
    return series


def _regional_survey_aggregate(
    world: World, mineral: str, region_id: str
) -> dict[str, Any]:
    """Mean / sampled-count of ``{mineral}_grade`` for *all* plots in ``region_id``.

    Note: this uses the world-authoritative subsurface, so it reports the
    objective average — a real economic actor would estimate this by paying
    for many surveys; the vendor abstracts that cost behind the product fee.
    """
    field = f"{mineral}_grade"
    w, h = _world_bounds(world)
    grades: list[float] = []
    for plot in world.plots.values():
        if region_for_coords(plot.x, plot.y, w, h) != region_id:
            continue
        if not hasattr(plot.subsurface, field):
            continue
        grades.append(float(getattr(plot.subsurface, field, 0.0)))
    avg = float(statistics.fmean(grades)) if grades else 0.0
    if avg >= 0.55:
        label = "high"
    elif avg >= 0.35:
        label = "moderate"
    else:
        label = "low"
    return {
        "region_id": region_id,
        "mineral": mineral,
        "field": field,
        "plots_sampled": len(grades),
        "avg_grade": round(avg, 4),
        "label": label,
    }


def _party_trade_volume_window(
    world: World, party: str, *, window_days: int
) -> dict[str, dict[str, int]]:
    """Aggregate ``party``'s buy/sell totals per material over the window.

    Returns ``{material: {"bought": int, "sold": int}}`` using the
    deterministic per-fill ``market_match`` events that the matching engine
    emits. ``market_buy`` aggregates are used as a fallback when a window
    has no per-fill rows.
    """
    cutoff = max(0, int(world.tick) - window_days * _TICKS_PER_GAME_DAY)
    totals: dict[str, dict[str, int]] = {}
    seen_match_materials: set[str] = set()
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < cutoff:
            break
        kind = str(ev.get("kind", ""))
        if kind not in ("market_match", "market_buy", "market_sell"):
            continue
        mat = str(ev.get("material") or "")
        if not mat:
            continue
        qty = 0
        for k in ("qty", "filled", "fill_qty"):
            v = ev.get(k)
            if v is None:
                continue
            try:
                qty = int(v)
            except (TypeError, ValueError):
                qty = 0
            if qty > 0:
                break
        if qty <= 0:
            continue
        if kind == "market_match":
            seen_match_materials.add(mat)
            buyer = str(ev.get("buyer") or "")
            seller = str(ev.get("seller") or "")
            if buyer == party:
                totals.setdefault(mat, {"bought": 0, "sold": 0})["bought"] += qty
            if seller == party:
                totals.setdefault(mat, {"bought": 0, "sold": 0})["sold"] += qty
        elif kind == "market_buy":
            # Only use buy aggregates for materials where we did NOT see per-fill rows
            # (older window where match-events were trimmed away).
            if mat in seen_match_materials:
                continue
            if str(ev.get("buyer") or ev.get("party") or "") != party:
                continue
            totals.setdefault(mat, {"bought": 0, "sold": 0})["bought"] += qty
        elif kind == "market_sell":
            if mat in seen_match_materials:
                continue
            if str(ev.get("party") or "") != party:
                continue
            totals.setdefault(mat, {"bought": 0, "sold": 0})["sold"] += qty
    return totals


def _classify_volume(qty: int) -> str:
    return "significant" if qty >= SIGNIFICANT_VOLUME_THRESHOLD else "minor"


def _party_volume_signal(
    world: World, party: str
) -> dict[str, Any]:
    """Categorical volume profile (no exact numbers in the public payload)."""
    totals = _party_trade_volume_window(world, party, window_days=PARTY_VOLUME_WINDOW_DAYS)
    profile: list[dict[str, str]] = []
    for mat in sorted(totals.keys()):
        rec = totals[mat]
        bought = int(rec.get("bought", 0))
        sold = int(rec.get("sold", 0))
        # Only "significant" lines appear in the output (the spec).
        if bought >= SIGNIFICANT_VOLUME_THRESHOLD:
            profile.append({"material": mat, "side": "buyer", "signal": _classify_volume(bought)})
        if sold >= SIGNIFICANT_VOLUME_THRESHOLD:
            profile.append({"material": mat, "side": "seller", "signal": _classify_volume(sold)})
    return {
        "party": party,
        "window_days": PARTY_VOLUME_WINDOW_DAYS,
        "profile": profile,
    }


def _supply_shortage_materials(world: World) -> list[str]:
    """Materials whose best-ask available units stayed < threshold for the last ``SHORTAGE_DAYS``.

    Uses ``world.market_history``: a snapshot per tick of ``best_asks_cents``
    per material. A material is "scarce" on a tick if it has < 10 *total* asked
    units on the ask side (we count the live book each tick).

    Live book: we read ``world.market_asks_by_material`` for the current tick
    plus the depth recorded in the ``scenario_state['supply_shortage_history']``
    accumulator which is updated at purchase time. To keep this product cheap
    and accurate, we sample directly from the live book + the recent history.
    """
    cutoff = max(0, int(world.tick) - SHORTAGE_DAYS * _TICKS_PER_GAME_DAY)
    # Materials seen in book history (either currently or in the past window).
    seen_materials: set[str] = set()
    for row in world.market_history:
        if int(row.get("tick", 0)) < cutoff:
            continue
        best_asks = row.get("best_asks_cents") or {}
        if isinstance(best_asks, dict):
            seen_materials.update(map(str, best_asks.keys()))
    for mat_key in world.market_asks_by_material.keys():
        seen_materials.add(str(mat_key))
    short: list[str] = []
    for mat in sorted(seen_materials):
        # Current depth — number of units across resting asks.
        asks = world.market_asks_by_material.get(mat, [])
        total_units = sum(int(o.qty) + int(o.iceberg_hidden_qty) for o in asks)
        if total_units < SHORTAGE_UNIT_THRESHOLD:
            short.append(mat)
    return short


# ───────────────────────── public entry point ─────────────────────────


def purchase_analytics_product(
    world: World,
    party: PartyId,
    product: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Charge ``party`` for ``product`` and return the analytics payload.

    Returns ``{ok: False, reason: str}`` on validation/cash errors.
    """
    if product not in _VALID_PRODUCTS:
        return {"ok": False, "reason": f"unknown analytics product: {product!r}"}
    cost = int(_PRODUCT_COSTS[product])
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    vendor = ANALYTICS_VENDOR_PARTY_ID
    if vendor not in world.parties:
        # Allow purchase even if the vendor wasn't seeded (frontier scenarios) —
        # cash goes to the system reserve so conservation still holds.
        vendor_cash = system_reserve_account()
    else:
        vendor_cash = party_cash_account(vendor)
    buyer_cash = party_cash_account(party)
    world.ledger.ensure_account(buyer_cash)
    if world.ledger.balance(buyer_cash) < cost:
        return {"ok": False, "reason": "insufficient cash for analytics"}
    params = dict(params or {})
    # Per-product input parsing first (fail before we charge cash).
    if product == "price_history":
        material = str(params.get("material", "")).strip()
        if not material:
            return {"ok": False, "reason": "missing material"}
    elif product == "regional_survey":
        mineral = str(params.get("mineral", "")).strip()
        region_id = str(params.get("region_id", "")).strip()
        if not mineral or not region_id:
            return {"ok": False, "reason": "missing mineral / region_id"}
    elif product == "party_volume":
        target_party = str(params.get("party_id", "")).strip()
        if not target_party:
            return {"ok": False, "reason": "missing party_id"}
    # Charge cash now (single transfer; consistent with intel.py).
    tr = world.ledger.transfer(
        debit=buyer_cash,
        credit=vendor_cash,
        amount_cents=cost,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    if product == "price_history":
        series = _price_history_for_material(world, str(params["material"]))
        data: dict[str, Any] = {
            "material": str(params["material"]),
            "window_days": PRICE_HISTORY_WINDOW_DAYS,
            "series": series,
            "point_count": len(series),
        }
    elif product == "regional_survey":
        data = _regional_survey_aggregate(
            world, str(params["mineral"]), str(params["region_id"])
        )
    elif product == "party_volume":
        data = _party_volume_signal(world, str(params["party_id"]))
    else:  # supply_shortage
        materials = _supply_shortage_materials(world)
        data = {"materials_in_shortage": materials, "threshold_units": SHORTAGE_UNIT_THRESHOLD}
    summary_bits: list[str] = []
    if product == "price_history":
        summary_bits.append(f"price_history {data['material']} ({len(data.get('series', []))} pts)")
    elif product == "regional_survey":
        summary_bits.append(
            f"regional_survey {data['mineral']} in {data['region_id']} "
            f"(avg {data['avg_grade']:.2f} — {data['label']})"
        )
    elif product == "party_volume":
        sigs = ", ".join(
            f"{p['material']} ({p['side']})" for p in data.get("profile", [])
        )
        summary_bits.append(f"party_volume {data['party']} — {sigs or 'no significant flows'}")
    else:
        summary_bits.append(
            f"supply_shortage — {len(data.get('materials_in_shortage', []))} material(s) "
            f"under {SHORTAGE_UNIT_THRESHOLD} units"
        )
    summary = "; ".join(summary_bits)
    record = {
        "tick": int(world.tick),
        "party": str(party),
        "product": product,
        "params": params,
        "cost_cents": cost,
        "summary": summary,
        "data": data,
    }
    world.analytics_purchases.append(record)
    if len(world.analytics_purchases) > 240:
        world.analytics_purchases = world.analytics_purchases[-240:]
    log_event(
        world,
        "analytics_purchase",
        f"{party} purchased {product} from {ANALYTICS_VENDOR_DISPLAY_NAME} "
        f"(${cost / 100:.2f}) — {summary}",
        party=str(party),
        product=product,
        cost_cents=cost,
    )
    return {
        "ok": True,
        "product": product,
        "cost_cents": cost,
        "data": data,
        "summary": summary,
    }

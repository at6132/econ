"""Genesis price model — fair-value table, exchange markup, settler cost-basis.

The clearinghouse (``genesis_exchange``) is a **backstop market-maker**, not the
primary price. Its ask is computed as ``producer_cost_basis × markup_factor`` —
markup tiered by material category (common / processed / rare-industrial) so the
exchange is **always more expensive than a real producer**. Settlers list below it
and still earn margin over their recipe cost. Hub demand walks the book
bottom-up, so settler clips strictly beat the exchange every tick.

Exchange prices are lagging indicators: ``tick_genesis_exchange_quoting`` re-anchors
the ask every ``EXCHANGE_PRICE_REFRESH_TICKS`` to the volume-weighted average of
recent fills (held flat if no fills). This makes the exchange slow to respond to
sudden real-market shifts — strategic by design.
"""

from __future__ import annotations

from realm.ids import MaterialId
from realm.recipes import RECIPES

# Reference midprice per material. These are the engine's "fair-value anchors";
# the exchange ask sits a spread above, settler cost-basis uses these for inputs.
# Sprint 1 nudged coal/timber/grain slightly upward to ensure hub willingness-to-pay
# (exchange_ask × 0.92) clears the spec's 75¢ floor for the player's coal strategy.
_FAIR_VALUE_CENTS: dict[str, int] = {
    "coal": 72,
    "electricity": 60,
    "grain": 140,
    "timber": 110,
    "stone": 48,
    "clay": 40,
    "iron_ore": 80,
    "copper_ore": 78,
    "lumber": 140,
    "flour": 110,
    "bread": 175,
    "brick": 130,
    "rope": 95,
    "iron_ingot": 460,
    "copper_ingot": 420,
    "charcoal": 78,
    "sand": 58,
    "limestone": 52,
    "slag": 24,
    "pottery": 105,
    "pick_axe": 695,
    "mining_pick": 1217,
    "spade": 521,
    "hand_saw": 782,
    # Tier-2 raws (high price — scarce, must be mined or bought dear)
    "sulfur_ore": 1_800,
    "saltpeter_ore": 2_200,
    "tin_ore": 1_600,
    "lead_ore": 1_400,
    "phosphate_ore": 1_200,
    "raw_silica": 900,
    # Processed Tier-2
    "pig_iron": 4_500,
    "cast_iron": 6_000,
    "bronze_ingot": 8_500,
    "tin_ingot": 3_800,
    "lead_ingot": 3_200,
    "sulfur_ore_refined": 3_400,
    "sulfuric_acid": 12_000,
    "refined_saltpeter": 5_000,
    "gunpowder": 15_000,
    "phosphate_meal": 3_500,
    "fused_silica": 9_000,
    # Tool components (intermediate goods)
    "pick_head": 3_200,
    "saw_blade": 3_800,
    "drill_bit": 6_500,
    "pump_unit": 18_000,
    "gear_set": 11_000,
}

# Legacy: exchange sat 15% above fair value (one-sided ask). Kept only as a
# fallback when neither cost-basis nor markup-tier is known for a material.
EXCHANGE_SPREAD_BPS: int = 1500

# Below this watermark of *non-exchange* resting ask units per material,
# the exchange tops up. Above it, settlers are supplying — exchange withdraws.
EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK: int = 16

# Floor margin a settler asks above their own marginal input cost (4%).
SETTLER_MARGIN_BPS: int = 400

# Lower floor as a fraction of fair value — prevents settlers from dumping
# downstream goods (timber, lumber, brick) far below the consensus print when
# their material-input cost is artificially low.
SETTLER_FAIR_VALUE_FLOOR_BPS: int = 8_500  # 85% of fair value

# ─────────────────── Markup-tier pricing (Sprint 1) ───────────────────
#
# ``exchange_ask = max(producer_cost_basis × markup_factor, fair_value × spread)``
# Tier the markup so common raws stay close to cost, while rare/industrial goods
# command a higher backstop margin (the exchange is the *most expensive* legal
# source, never the default). Materials not listed below default to TIER_COMMON.

EXCHANGE_MARKUP_TIER_COMMON_BPS: int = 12_500   # 1.25× (coal, timber, grain, ores)
EXCHANGE_MARKUP_TIER_PROCESSED_BPS: int = 14_000  # 1.40× (ingots, lumber, brick)
EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS: int = 16_000  # 1.60× (wire, electricity, tools)

# Hubs walk the book; they pay any ask but cap their willingness at a discount
# vs the exchange so a polluted book never drains pop hubs.
HUB_MAX_BID_BPS_OF_EXCHANGE: int = 9_200  # 0.92× the exchange ask

# How often the exchange re-anchors its ask off the realised market average.
EXCHANGE_PRICE_REFRESH_TICKS: int = 14_400  # 10 game-days @ 1440 ticks/day

# Listing controls (managed mode). Smaller per-clip caps + relist cooldown so
# real producers can outpace the exchange in steady-state.
EXCHANGE_LISTING_MAX_QTY_PER_CLIP: int = 20
EXCHANGE_RELIST_COOLDOWN_TICKS: int = 30

# Withdrawal heuristic (managed → unmanaged transition).
EXCHANGE_WITHDRAW_MIN_DISTINCT_SELLERS: int = 3
EXCHANGE_RESTORE_MAX_DISTINCT_SELLERS: int = 1  # < 2 ⇒ ≤1 distinct sellers
EXCHANGE_SELLER_WINDOW_TICKS: int = 7 * 1440  # 7 game-days
EXCHANGE_RESTORE_LOW_DAYS: int = 3  # consecutive days under the floor → restore
EXCHANGE_UNMANAGED_RESERVE_UNITS: int = 50  # finite pool while withdrawn

# Markup tier table — explicit categorisation. Anything not listed falls to
# TIER_COMMON. Keep this list aligned with the staples list in
# ``genesis_exchange_liquidity._STAPLES``.
_MARKUP_TIER_BY_MATERIAL: dict[str, int] = {
    # Common raws
    "coal": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "timber": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "grain": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "iron_ore": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "copper_ore": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "stone": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "clay": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "sand": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "limestone": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    "charcoal": EXCHANGE_MARKUP_TIER_COMMON_BPS,
    # Processed
    "iron_ingot": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "steel_ingot": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "copper_ingot": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "lumber": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "brick": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "flour": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "bread": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "pottery": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "rope": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "mortar": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "quicklime": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    "glass": EXCHANGE_MARKUP_TIER_PROCESSED_BPS,
    # Rare / industrial
    "copper_wire": EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS,
    "electricity": EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS,
    "pick_axe": EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS,
    "mining_pick": EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS,
    "spade": EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS,
    "hand_saw": EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS,
    "ladder": EXCHANGE_MARKUP_TIER_INDUSTRIAL_BPS,
}


def markup_factor_bps(material: MaterialId) -> int:
    """Pick the markup tier for ``material``; falls back to common (1.25×)."""
    return _MARKUP_TIER_BY_MATERIAL.get(str(material), EXCHANGE_MARKUP_TIER_COMMON_BPS)


def producer_cost_basis_cents(material: MaterialId) -> int | None:
    """Cheapest input-only cost per output unit, across all recipes that produce
    ``material``. Labor is intentionally excluded — labor cents are paid to the
    system reserve (no employees) or split across employees (with employees), so
    it represents distributed wage payment rather than a *marginal* cost the
    producer must recoup unit-for-unit. Markup over this floor is what gives a
    real producer headroom over the clearinghouse.

    Hand recipes are skipped (they encode hand-tool costs separately).
    """
    best: int | None = None
    for recipe in RECIPES.values():
        if recipe.requires_tool is not None:
            continue
        out_qty = int(recipe.outputs.get(material, 0))
        if out_qty <= 0:
            continue
        input_cost = 0
        ok = True
        for in_mat, in_qty in recipe.inputs.items():
            unit = _FAIR_VALUE_CENTS.get(str(in_mat))
            if unit is None:
                ok = False
                break
            input_cost += unit * int(in_qty)
        if not ok:
            continue
        # Ceil division so per_unit covers the integer rounding losses on inputs.
        per_unit = (input_cost + out_qty - 1) // out_qty
        if best is None or per_unit < best:
            best = per_unit
    return best


def hub_max_bid_cents(material: MaterialId) -> int:
    """Ceiling price a pop-hub buyer is willing to pay.

    Anchored at ``exchange_ask × 0.92`` so settlers undercutting the exchange
    automatically clear, while a polluted book (e.g. a single absurd ask) can't
    drain hub wallets at usurious prices.
    """
    ex = exchange_ask_cents(material)
    return max(4, (int(ex) * HUB_MAX_BID_BPS_OF_EXCHANGE) // 10_000)

# Hard fallback list price when neither fair value nor recipe cost is known.
_FALLBACK_LIST_CENTS: dict[str, int] = {
    "coal": 58,
    "timber": 90,
    "grain": 120,
    "electricity": 50,
    "stone": 44,
    "clay": 36,
    "iron_ore": 72,
    "copper_ore": 70,
    "flour": 95,
    "bread": 140,
    "brick": 110,
    "lumber": 125,
    "rope": 85,
    "iron_ingot": 420,
    "copper_ingot": 380,
    "charcoal": 70,
    "sand": 55,
    "limestone": 48,
    "slag": 25,
    "pottery": 90,
    "pick_axe": 780,
    "mining_pick": 1350,
    "spade": 580,
    "hand_saw": 870,
    "sulfur_ore": 1_950,
    "saltpeter_ore": 2_400,
    "tin_ore": 1_750,
    "lead_ore": 1_550,
    "phosphate_ore": 1_350,
    "raw_silica": 1_050,
    "pig_iron": 5_000,
    "cast_iron": 6_400,
    "bronze_ingot": 8_900,
    "tin_ingot": 4_000,
    "lead_ingot": 3_400,
    "sulfur_ore_refined": 3_600,
    "sulfuric_acid": 12_500,
    "refined_saltpeter": 5_300,
    "gunpowder": 15_400,
    "phosphate_meal": 3_800,
    "fused_silica": 9_400,
    "pick_head": 3_400,
    "saw_blade": 4_000,
    "drill_bit": 6_700,
    "pump_unit": 18_500,
    "gear_set": 11_500,
}


def fair_value_cents(material: MaterialId) -> int | None:
    return _FAIR_VALUE_CENTS.get(str(material))


def _baseline_exchange_ask_cents(material: MaterialId) -> int:
    """Static markup-over-cost ask (no recent-fills override applied)."""
    basis = producer_cost_basis_cents(material)
    fv = _FAIR_VALUE_CENTS.get(str(material))
    fb = _FALLBACK_LIST_CENTS.get(str(material))
    tier = markup_factor_bps(material)
    candidates: list[int] = []
    if basis is not None:
        candidates.append((basis * tier + 9_999) // 10_000)
    if fv is not None:
        # Legacy spread floor — keeps the exchange above fair value even when
        # the cost-basis path is shallow (e.g. for extraction recipes where
        # input costs are tiny but fair value is meaningful).
        candidates.append((fv * (10_000 + EXCHANGE_SPREAD_BPS) + 9_999) // 10_000)
    if fb is not None:
        candidates.append(int(fb))
    if not candidates:
        return 4
    return max(4, max(candidates))


def exchange_ask_cents(material: MaterialId, *, world=None) -> int:
    """Clearinghouse ask price.

    If ``world`` is provided and the exchange has a freshly-anchored price for
    this material in ``world.scenario_state["exchange"]["price"]``, prefer that
    (it reflects the lagging 10-day market average). Otherwise compute the
    static markup-over-cost baseline.
    """
    if world is not None:
        ex_state = (world.scenario_state.get("exchange") or {}) if world.scenario_state else {}
        price_map = ex_state.get("price") or {}
        anchored = price_map.get(str(material))
        if isinstance(anchored, int) and anchored > 0:
            return int(anchored)
    return _baseline_exchange_ask_cents(material)


def _recipe_unit_input_cost_cents(material: MaterialId) -> int | None:
    """
    Cheapest recipe path producing ``material`` at fair-value **input** prices.

    Labor is treated as overhead, not marginal cost, so this represents the
    minimum-clearing price below which a settler trade destroys value.
    """
    best: int | None = None
    for recipe in RECIPES.values():
        if recipe.requires_tool is not None:
            continue
        out_qty = int(recipe.outputs.get(material, 0))
        if out_qty <= 0:
            continue
        input_cost = 0
        ok = True
        for in_mat, in_qty in recipe.inputs.items():
            unit = _FAIR_VALUE_CENTS.get(str(in_mat))
            if unit is None:
                ok = False
                break
            input_cost += unit * int(in_qty)
        if not ok:
            continue
        per_unit = (input_cost + out_qty - 1) // out_qty  # ceil; conservative
        if best is None or per_unit < best:
            best = per_unit
    return best


def settler_cost_basis_cents(material: MaterialId) -> int | None:
    """Marginal input cost per unit at fair-value input prices (excludes labor overhead)."""
    return _recipe_unit_input_cost_cents(material)


def settler_ask_cents(world, material: MaterialId, *, best_resting_bid: int | None = None) -> int:
    """
    Settler limit-sell price.

    - **Floor** = ``max(input_cost × 1.04, fair_value × 0.85)`` — never destroy value,
      never dump downstream goods far below consensus.
    - **Ceiling** = ``exchange_ask − 2`` — strictly beat the clearinghouse on price-time.
    - If a real bid sits at or above floor, **lift it** (``bid + 1¢``, capped at ceiling).
    - Else sit at the ceiling so price-time priority routes hub demand to settlers.

    Decoupled from ``best_resting_ask`` — settlers no longer anchor to (and tie) the
    exchange's quote.
    """
    cost = _recipe_unit_input_cost_cents(material)
    fv = _FAIR_VALUE_CENTS.get(str(material))
    if cost is None and fv is None:
        return max(4, _FALLBACK_LIST_CENTS.get(str(material), 40))
    cost_floor = (
        (int(cost) * (10_000 + SETTLER_MARGIN_BPS) + 9_999) // 10_000
        if cost is not None
        else 0
    )
    fv_floor = (
        (int(fv) * SETTLER_FAIR_VALUE_FLOOR_BPS + 9_999) // 10_000
        if fv is not None
        else 0
    )
    floor = max(4, cost_floor, fv_floor)
    if fv is not None:
        ceiling = max(floor, exchange_ask_cents(material, world=world) - 2)
    else:
        ceiling = max(floor, _FALLBACK_LIST_CENTS.get(str(material), floor))
    if best_resting_bid is not None and int(best_resting_bid) >= floor:
        return max(floor, min(ceiling, int(best_resting_bid) + 1))
    return ceiling

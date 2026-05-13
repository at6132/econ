"""Genesis price model — fair-value table, exchange spread, settler cost-basis.

The clearinghouse (``genesis_exchange``) is a **backstop market-maker**, not the
primary price. It quotes asks at ``fair_value × (1 + EXCHANGE_SPREAD_BPS / 10_000)``
so real producers (settlers) can list **below** it and still earn margin over
their recipe cost. Hub demand walks the book bottom-up, so a settler-priced clip
strictly beats the exchange clip at the same material every tick.
"""

from __future__ import annotations

from realm.ids import MaterialId
from realm.recipes import RECIPES

# Reference midprice per material. These are the engine's "fair-value anchors";
# the exchange ask sits a spread above, settler cost-basis uses these for inputs.
_FAIR_VALUE_CENTS: dict[str, int] = {
    "coal": 62,
    "electricity": 52,
    "grain": 128,
    "timber": 96,
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
}

# Exchange sits 15% above fair value (one-sided ask). Settlers operate in
# [cost_basis × 1.04, exchange_ask − 2¢], beating the clearinghouse on price-time.
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
}


def fair_value_cents(material: MaterialId) -> int | None:
    return _FAIR_VALUE_CENTS.get(str(material))


def exchange_ask_cents(material: MaterialId) -> int:
    """Clearinghouse ask: ``fair_value × (1 + spread)``; falls back to fair value if unknown."""
    fv = _FAIR_VALUE_CENTS.get(str(material))
    if fv is None:
        return 4
    return max(4, (fv * (10_000 + EXCHANGE_SPREAD_BPS) + 9_999) // 10_000)


def _recipe_unit_input_cost_cents(material: MaterialId) -> int | None:
    """
    Cheapest recipe path producing ``material`` at fair-value **input** prices.

    Labor is treated as overhead, not marginal cost, so this represents the
    minimum-clearing price below which a settler trade destroys value.
    """
    best: int | None = None
    for recipe in RECIPES.values():
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
        ceiling = max(floor, exchange_ask_cents(material) - 2)
    else:
        ceiling = max(floor, _FALLBACK_LIST_CENTS.get(str(material), floor))
    if best_resting_bid is not None and int(best_resting_bid) >= floor:
        return max(floor, min(ceiling, int(best_resting_bid) + 1))
    return ceiling

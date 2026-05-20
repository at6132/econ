"""
Market oracle — a lightweight, shared market snapshot for NPC decision-making.

Computed once per game-day (every 1440 ticks). All NPCs read from it.
Never recomputed mid-day, so NPC decisions are based on yesterday's prices.
This is realistic (information delay) and free (O(1) reads).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from realm.materials import all_material_ids
from realm.world import World

_GENESIS_FAIR_VALUE: dict[str, int] = {
    "iron_ingot": 340,
    "steel_ingot": 480,
    "copper_ingot": 280,
    "tin_ingot": 220,
    "lead_ingot": 185,
    "bronze_ingot": 320,
    "pig_iron": 260,
    "cast_iron": 345,
    "iron_ore": 120,
    "coal": 90,
    "timber": 130,
    "lumber": 400,
    "grain": 165,
    "bread": 280,
    "flour": 220,
    "brick": 155,
    "stone": 110,
    "clay": 100,
    "sand": 80,
    "limestone": 95,
    "glass": 380,
    "electricity": 70,
    "charcoal": 160,
    "rope": 320,
    "medicine": 460,
    "mortar": 210,
    "quicklime": 190,
    "copper_ore": 150,
    "tin_ore": 185,
    "lead_ore": 160,
    "sulfur_ore": 210,
    "phosphate_ore": 140,
    "saltpeter_ore": 255,
    "pick_axe": 540,
    "hand_saw": 640,
    "drill_bit": 750,
    "mining_pick": 540,
    "spade": 300,
    "ladder": 280,
    "vessel": 2800,
    "small_vessel": 1800,
    "copper_wire": 420,
    "gear_set": 1200,
    "pump_unit": 1500,
    "saw_blade": 440,
    "pick_head": 370,
    "pottery": 280,
    "fish": 190,
    "smoked_fish": 420,
    "wild_herb": 240,
    "shale_oil": 380,
}


@dataclass
class MarketOracle:
    """Read-only market snapshot. Rebuilt once per game-day."""

    computed_at_tick: int = 0
    best_ask: dict[str, int] = field(default_factory=dict)
    best_bid: dict[str, int] = field(default_factory=dict)
    ask_volume: dict[str, int] = field(default_factory=dict)
    ask_depth: dict[str, int] = field(default_factory=dict)
    bid_depth: dict[str, int] = field(default_factory=dict)
    ask_seller_count: dict[str, int] = field(default_factory=dict)
    price_spread_pct: dict[str, float] = field(default_factory=dict)
    scarce: set[str] = field(default_factory=set)
    flooded: set[str] = field(default_factory=set)
    recipe_margins: dict[str, float] = field(default_factory=dict)
    game_day: int = 0


_oracle: MarketOracle = MarketOracle(computed_at_tick=-1)


def get_oracle(world: World) -> MarketOracle:
    """Return the current oracle. Rebuilds if stale (new game-day)."""
    global _oracle
    current_day = int(world.tick) // 1440
    if _oracle.game_day == current_day and _oracle.computed_at_tick >= 0:
        return _oracle
    _oracle = _build_oracle(world, current_day)
    return _oracle


def _material_price(
    oracle: MarketOracle,
    mid: str,
    *,
    for_output: bool,
) -> int:
    """Fair value for margin math: bid→ask→genesis fair value (outputs); ask→bid→fair (inputs)."""
    if for_output:
        return (
            oracle.best_bid.get(mid)
            or oracle.best_ask.get(mid)
            or _GENESIS_FAIR_VALUE.get(mid, 0)
        )
    return (
        oracle.best_ask.get(mid)
        or oracle.best_bid.get(mid)
        or _GENESIS_FAIR_VALUE.get(mid, 0)
    )


def _input_cost_cents(oracle: MarketOracle, recipe: object) -> int:
    total = int(getattr(recipe, "labor_cents", 0))
    for mat, qty in getattr(recipe, "inputs", {}).items():
        mid = str(mat)
        total += _material_price(oracle, mid, for_output=False) * int(qty)
    return total


def _output_value_cents(oracle: MarketOracle, recipe: object) -> int:
    total = 0
    for mat, qty in getattr(recipe, "outputs", {}).items():
        mid = str(mat)
        total += _material_price(oracle, mid, for_output=True) * int(qty)
    return total


def _build_oracle(world: World, game_day: int) -> MarketOracle:
    from realm.production.recipes import RECIPES

    oracle = MarketOracle(
        computed_at_tick=int(world.tick),
        game_day=game_day,
    )

    for mat in all_material_ids():
        mid = str(mat)
        asks = world.market_asks_by_material.get(mid, [])
        if not asks:
            asks = world.market_asks_by_material.get(mat, [])
        bids = world.market_bids_by_material.get(mid, [])
        if not bids:
            bids = world.market_bids_by_material.get(mat, [])
        if asks:
            oracle.best_ask[mid] = min(int(a.price_per_unit_cents) for a in asks)
            oracle.ask_volume[mid] = sum(int(a.qty) for a in asks)
            oracle.ask_depth[mid] = sum(int(a.qty) for a in asks)
            oracle.ask_seller_count[mid] = len({a.party for a in asks})
        if bids:
            oracle.best_bid[mid] = max(int(b.max_price_per_unit_cents) for b in bids)
            oracle.bid_depth[mid] = sum(int(b.qty) for b in bids)
        if oracle.best_ask.get(mid) and oracle.best_bid.get(mid):
            spread = (oracle.best_ask[mid] - oracle.best_bid[mid]) / oracle.best_ask[mid]
            oracle.price_spread_pct[mid] = round(spread, 4)

    scarcity_tracker: dict[str, int] = world.scenario_state.setdefault(
        "oracle_scarcity_days", {}
    )
    for mid, vol in oracle.ask_volume.items():
        if vol < 15:
            scarcity_tracker[mid] = int(scarcity_tracker.get(mid, 0)) + 1
            if scarcity_tracker[mid] >= 2:
                oracle.scarce.add(mid)
        else:
            scarcity_tracker[mid] = 0
        if vol > 200:
            oracle.flooded.add(mid)

    for rid, recipe in RECIPES.items():
        input_cost = _input_cost_cents(oracle, recipe)
        output_value = _output_value_cents(oracle, recipe)
        if input_cost > 0:
            oracle.recipe_margins[rid] = (output_value - input_cost) / input_cost
        else:
            oracle.recipe_margins[rid] = 0.0 if output_value == 0 else 1.0

    return oracle

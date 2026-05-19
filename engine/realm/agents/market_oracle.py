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


@dataclass
class MarketOracle:
    """Read-only market snapshot. Rebuilt once per game-day."""

    computed_at_tick: int = 0
    best_ask: dict[str, int] = field(default_factory=dict)
    best_bid: dict[str, int] = field(default_factory=dict)
    ask_volume: dict[str, int] = field(default_factory=dict)
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
        if bids:
            oracle.best_bid[mid] = max(int(b.max_price_per_unit_cents) for b in bids)

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
        input_cost = 0
        for mat, qty in recipe.inputs.items():
            price = oracle.best_ask.get(str(mat), 99_999)
            input_cost += price * int(qty)
        input_cost += int(recipe.labor_cents)

        output_value = 0
        for mat, qty in recipe.outputs.items():
            bid = oracle.best_bid.get(str(mat))
            price = bid if bid is not None else oracle.best_ask.get(str(mat), 0)
            output_value += int(price) * int(qty)

        if input_cost > 0:
            oracle.recipe_margins[rid] = (output_value - input_cost) / input_cost
        else:
            oracle.recipe_margins[rid] = 0.0 if output_value == 0 else 1.0

    return oracle

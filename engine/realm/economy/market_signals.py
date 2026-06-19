"""Market imbalance signals — bid/ask depth and scarcity for NPC + store loops."""

from __future__ import annotations

from typing import Final

from realm.core.ids import MaterialId
from realm.events.event_log import log_event
from realm.economy.markets import best_resting_ask_cents, best_resting_bid_cents
from realm.economy.pricing import exchange_ask_cents, fair_value_cents
from realm.world import World

STAPLE_MATERIALS: Final[frozenset[str]] = frozenset(
    {
        "coal",
        "grain",
        "timber",
        "lumber",
        "iron_ore",
        "flour",
        "bread",
        "fish",
    }
)

# Positive bps ⇒ bid depth exceeds ask depth (demand pressure).
_IMBALANCE_SCALE: Final[int] = 10_000
_ASK_FIRST_IMBALANCE_BPS: Final[int] = 800  # supply-side listing when not hot


def bid_depth_units(world: World, material: MaterialId) -> int:
    bids = world.market_bids_by_material.get(str(material), [])
    return sum(int(b.qty) + int(getattr(b, "iceberg_hidden_qty", 0) or 0) for b in bids)


def ask_depth_units(world: World, material: MaterialId) -> int:
    asks = world.market_asks_by_material.get(str(material), [])
    return sum(int(a.qty) + int(getattr(a, "iceberg_hidden_qty", 0) or 0) for a in asks)


def demand_supply_imbalance_bps(world: World, material: MaterialId) -> int:
    """Demand minus supply on the resting book, in basis points of total depth."""
    bid = bid_depth_units(world, material)
    ask = ask_depth_units(world, material)
    total = bid + ask
    if total <= 0:
        return 5_000  # no book — treat as latent demand
    return ((bid - ask) * _IMBALANCE_SCALE) // total


def scarcity_premium_bps(world: World, material: MaterialId) -> int:
    """Extra bid markup when asks are thin vs fair value."""
    ask_px = best_resting_ask_cents(world, material)
    fair = int(fair_value_cents(material) or exchange_ask_cents(material, world=world))
    if ask_px is None:
        return 1_200
    if fair <= 0:
        return 0
    if ask_px <= fair:
        return 0
    overshoot = ask_px - fair
    return min(2_500, (overshoot * 10_000) // max(1, fair))


def equilibrium_ask_cents(world: World, material: MaterialId) -> int:
    """Target list price when closing a surplus — fair value, capped by best bid."""
    fair = int(fair_value_cents(material) or exchange_ask_cents(material, world=world))
    bid_px = best_resting_bid_cents(world, material)
    ask_px = best_resting_ask_cents(world, material)
    target = fair
    if bid_px is not None and bid_px > 0:
        target = min(target, int(bid_px) + 2)
    if ask_px is not None and ask_px > 0:
        target = min(target, int(ask_px))
    return max(4, target)


def should_list_ask_before_bids(world: World, material: MaterialId) -> bool:
    """When False, sellers hit bids first (demand-heavy market)."""
    if str(material) not in STAPLE_MATERIALS:
        return False
    return demand_supply_imbalance_bps(world, material) <= _ASK_FIRST_IMBALANCE_BPS


def note_supply_capacity_feed(
    world: World,
    party: str,
    *,
    building_id: str,
    output_material: MaterialId,
) -> None:
    """Public feed when new production capacity lands (affects expectations)."""
    if world.scenario_id != "genesis":
        return
    gst = world.scenario_state.setdefault("genesis", {})
    if not isinstance(gst, dict):
        return
    key = f"feed_capacity:{building_id}:{party}"
    announced = gst.setdefault("feed_capacity_announced", [])
    if not isinstance(announced, list):
        announced = []
        gst["feed_capacity_announced"] = announced
    if key in announced:
        return
    announced.append(key)
    pretty_b = building_id.replace("_", " ")
    pretty_m = str(output_material).replace("_", " ")
    log_event(
        world,
        "world_feed",
        f"New {pretty_b} capacity ({party}) — {pretty_m} supply expected to rise on the frontier.",
        feed_source="supply_capacity",
        party=str(party),
        building_id=building_id,
        material=str(output_material),
    )


__all__ = [
    "STAPLE_MATERIALS",
    "bid_depth_units",
    "ask_depth_units",
    "demand_supply_imbalance_bps",
    "scarcity_premium_bps",
    "equilibrium_ask_cents",
    "should_list_ask_before_bids",
    "note_supply_capacity_feed",
]

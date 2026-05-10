"""Tier 2 optimizing agents — five algorithmic loops (Phase 2 / doc 06).

Unlike Tier 1 fixed cadence shoppers, these roles read the live book and adjust
limits (escrow discipline, spread capture, inventory bias). All randomness uses
``world.rng("tier2:…")`` so replays stay deterministic.

Archetypes:

- **t2_ele_bidstack** — cancels stale electricity bids then posts a small clip at a
  limit derived from the current best ask (adds depth without lifting the market).
- **t2_lumber_bid** — when the lumber spread is wide, improves the bid side by one
  cent with a single resting order.
- **t2_timber_spread** — with on-hand timber, cancels and replaces asks using nearby
  bid quotes plus bounded jitter.
- **t2_clay_sweep** — accumulates clay when visible asks are below a conservative
  threshold (sweep size capped per tick).
- **t2_coal_spread** — with on-hand coal, cancels and replaces asks using nearby bid
  quotes plus bounded jitter (parallel to timber, different cadence / RNG namespace).
"""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import (
    cancel_party_asks_for_material,
    cancel_party_bids_for_material,
    market_buy,
    place_buy_order,
    place_sell_order,
)
from realm.world import World


def _best_resting_ask(world: World, material: MaterialId) -> int | None:
    lst = world.market_asks_by_material.get(str(material), [])
    if not lst:
        return None
    return min(o.price_per_unit_cents for o in lst)


def _best_resting_bid(world: World, material: MaterialId) -> int | None:
    lst = world.market_bids_by_material.get(str(material), [])
    if not lst:
        return None
    return max(b.max_price_per_unit_cents for b in lst)


def _ele_bidstack(world: World) -> None:
    if world.tick % 20 != 0:
        return
    party = PartyId("t2_ele_bidstack")
    if party not in world.parties:
        return
    mat = MaterialId("electricity")
    cancel_party_bids_for_material(world, party, mat)
    best_ask = _best_resting_ask(world, mat)
    if best_ask is None:
        limit = 22
    else:
        jitter = world.rng("tier2:ele:lim").randint(0, 4)
        limit = max(18, best_ask - 10 + jitter)
    place_buy_order(world, party, mat, 2, limit)


def _lumber_bid_improver(world: World) -> None:
    if world.tick % 24 != 0:
        return
    party = PartyId("t2_lumber_bid")
    if party not in world.parties:
        return
    mat = MaterialId("lumber")
    best_ask = _best_resting_ask(world, mat)
    best_bid = _best_resting_bid(world, mat)
    if best_ask is None or best_bid is None:
        return
    if best_ask - best_bid < 3:
        return
    new_px = best_bid + 1
    if new_px >= best_ask:
        return
    cancel_party_bids_for_material(world, party, mat)
    place_buy_order(world, party, mat, 1, new_px)


def _timber_spread_trader(world: World) -> None:
    if world.tick % 21 != 0:
        return
    party = PartyId("t2_timber_spread")
    if party not in world.parties:
        return
    mat = MaterialId("timber")
    if world.inventory.qty(party, mat) < 1:
        return
    cancel_party_asks_for_material(world, party, mat)
    best_bid = _best_resting_bid(world, mat)
    best_ask = _best_resting_ask(world, mat)
    if best_bid is None:
        px = 68 + world.rng("tier2:ts:px").randint(0, 6)
    else:
        px = best_bid + world.rng("tier2:ts:px").randint(1, 4)
    if best_ask is not None:
        px = min(px, best_ask - 1)
    if px < 12:
        return
    place_sell_order(world, party, mat, 1, px)


def _clay_sweep(world: World) -> None:
    if world.tick % 18 != 0:
        return
    party = PartyId("t2_clay_sweep")
    if party not in world.parties:
        return
    mat = MaterialId("clay")
    best_ask = _best_resting_ask(world, mat)
    if best_ask is None or best_ask > 54:
        return
    market_buy(world, party, mat, 1)


def _coal_spread_trader(world: World) -> None:
    if world.tick % 23 != 0:
        return
    party = PartyId("t2_coal_spread")
    if party not in world.parties:
        return
    mat = MaterialId("coal")
    if world.inventory.qty(party, mat) < 1:
        return
    cancel_party_asks_for_material(world, party, mat)
    best_bid = _best_resting_bid(world, mat)
    best_ask = _best_resting_ask(world, mat)
    if best_bid is None:
        px = 34 + world.rng("tier2:coal_spread:px").randint(0, 6)
    else:
        px = best_bid + world.rng("tier2:coal_spread:px").randint(1, 3)
    if best_ask is not None:
        px = min(px, best_ask - 1)
    if px < 8:
        return
    place_sell_order(world, party, mat, 1, px)


def tick_tier2_agents(world: World) -> None:
    """Run Tier 2 decision loops once per simulation tick."""
    _ele_bidstack(world)
    _lumber_bid_improver(world)
    _timber_spread_trader(world)
    _clay_sweep(world)
    _coal_spread_trader(world)

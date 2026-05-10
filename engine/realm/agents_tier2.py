"""Tier 2 optimizing agents (``realm_docs/06_AI_AGENT_DESIGN.md`` — Tier 2).

These are **algorithmic** NPCs: each archetype implements a narrow optimization or
search policy over the **live** order book and inventory (spread capture, depth at
stale quotes, conservative sweeps). They use the same market primitives as players
(Tier 1 is reactive cadence + ``market_buy``; Tier 2 **reads quotes** and adjusts
limits). This module is Phase 2 scope: small handcrafted solvers and bounded heuristics,
not full RL — doc 06’s “memory / KPI history / CPU budget” hooks are represented only
implicitly (cadence, caps, and RNG namespaces).

**Determinism:** all stochastic tie-breaks use ``world.rng("tier2:…")`` — no
``random`` module or wall-clock noise.

Archetypes (problem sketch → behavior):

- **t2_ele_bidstack** — depth on electricity: cancel own bids, repost a short clip at a
  limit anchored to the best ask (or a floor when the ask side is empty).
- **t2_lumber_bid** — wide-spread lumber: improve the best bid by one cent with one
  resting bid when bid–ask gap is large enough.
- **t2_timber_spread** — inventory timber: refresh the ask off nearby bids with bounded
  price jitter under the best ask.
- **t2_clay_sweep** — accumulate clay when the best ask is at or below a conservative
  ceiling (one unit per eligible tick).
- **t2_coal_spread** — inventory coal: same pattern as timber with a separate cadence
  and RNG namespace.
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

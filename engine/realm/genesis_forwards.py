"""Settler + consolidator forward-contract behaviour (Sprint 4 — Phase C.4).

Two agent behaviours sit on top of the forward-contract primitives in
``contract_stubs``:

1. **Settlers** with a consistent production surplus occasionally propose a
   forward contract to **Kessler Industrial (the consolidator)** at +5 %
   over current spot. (Pre-Phase 7 this used to target ``pop_hub_e``;
   with hubs removed Kessler is the natural counter-party — they're
   the entrepreneur NPC that already accumulates raw materials.)
   Probability is 10 % per game-day per qualifying settler.
2. **Kessler Industrial** proposes forward contracts to *buy* its key input
   below current spot — offering certainty of payment in exchange for a small
   discount. Used to lock in supply chains.

Both behaviours use the deterministic ``world.rng`` so identical seeds produce
identical histories.
"""

from __future__ import annotations

from typing import Final

from realm.contract_stubs import propose_forward_contract, accept_forward_contract
from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.ledger import party_cash_account
from realm.markets import best_resting_ask_cents
from realm.world import World


__all__ = [
    "SETTLER_FORWARD_PROB_PER_GAME_DAY",
    "SETTLER_FORWARD_PREMIUM_BPS",
    "CONSOLIDATOR_FORWARD_DISCOUNT_BPS",
    "tick_settler_forward_proposals",
    "tick_consolidator_forward_proposals",
]


_TICKS_PER_GAME_DAY: Final[int] = 1440

SETTLER_FORWARD_PROB_PER_GAME_DAY: float = 0.10
SETTLER_FORWARD_PREMIUM_BPS: int = 500  # +5 % above current spot
SETTLER_FORWARD_QTY: int = 20  # standard tranche size for a settler forward
SETTLER_FORWARD_HORIZON_TICKS: int = 10 * _TICKS_PER_GAME_DAY
SETTLER_SURPLUS_MIN_UNITS: int = 12

CONSOLIDATOR_FORWARD_DISCOUNT_BPS: int = 400  # 4 % below current spot
CONSOLIDATOR_FORWARD_QTY: int = 30
CONSOLIDATOR_FORWARD_HORIZON_TICKS: int = 8 * _TICKS_PER_GAME_DAY


# ─────────────────── settlers ───────────────────


def _settler_active_forward_count(world: World, settler: str) -> int:
    return sum(
        1
        for c in world.contracts
        if str(c.get("kind", "")) == "forward_contract"
        and str(c.get("seller", "")) == settler
        and str(c.get("status", "")) in ("proposed", "active")
    )


def _settler_surplus_material(world: World, settler: PartyId) -> tuple[str, int] | None:
    """Pick the settler's most-stocked tradeable output (≥ surplus minimum)."""
    stock = world.inventory.stock.get(settler, {}) or {}
    if not stock:
        return None
    candidates = [
        (str(mid), int(qty))
        for mid, qty in stock.items()
        if int(qty) >= SETTLER_SURPLUS_MIN_UNITS
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[1], x[0]))
    return candidates[0]


def tick_settler_forward_proposals(world: World) -> None:
    """One pass per game-day. Run after the settler business loop so output
    stock is up-to-date for the surplus check."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    # Phase 7A: target the consolidator (Kessler Industrial) instead of the
    # removed pop_hub_e. The consolidator already accumulates raw materials
    # at scale — they're the natural buyer for settler surplus.
    try:
        from realm.genesis_consolidator import CONSOLIDATOR_PARTY_ID
    except ImportError:
        return
    buyer = CONSOLIDATOR_PARTY_ID if CONSOLIDATOR_PARTY_ID in world.parties else None
    if buyer is None:
        return
    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")),
        key=str,
    )
    for settler in settlers:
        if _settler_active_forward_count(world, str(settler)) >= 1:
            continue
        surplus = _settler_surplus_material(world, settler)
        if surplus is None:
            continue
        material_s, available = surplus
        rng = world.rng(f"forward_proposal:{settler}:{world.tick}")
        if rng.random() >= SETTLER_FORWARD_PROB_PER_GAME_DAY:
            continue
        spot = best_resting_ask_cents(world, MaterialId(material_s))
        if spot is None or spot <= 0:
            continue
        price = max(2, (int(spot) * (10_000 + SETTLER_FORWARD_PREMIUM_BPS)) // 10_000)
        qty = min(SETTLER_FORWARD_QTY, max(8, available // 2))
        delivery = int(world.tick) + SETTLER_FORWARD_HORIZON_TICKS
        prop = propose_forward_contract(
            world,
            settler,
            buyer,
            MaterialId(material_s),
            int(qty),
            int(price),
            delivery,
        )
        if not prop.get("ok"):
            continue
        # The consolidator auto-accepts settler forwards — they value the
        # supply commitment more than the small premium.
        cid = str(prop.get("contract_id", ""))
        accept_forward_contract(world, buyer, cid)


# ─────────────────── consolidator ───────────────────


def tick_consolidator_forward_proposals(world: World) -> None:
    """Consolidator proposes a forward to *buy* its target_input below spot.

    Runs once per game-day. If the key input is currently tracked, it
    proposes the forward to a randomly-selected settler-seller (deterministic
    via world rng). Settlers auto-accept these — guaranteed cash + locked
    price below their current cost-basis-derived ask is attractive when they
    have the surplus.
    """
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    try:
        from realm.genesis_consolidator import CONSOLIDATOR_PARTY_ID, consolidator_state
    except ImportError:
        return
    if CONSOLIDATOR_PARTY_ID not in world.parties:
        return
    state = consolidator_state(world)
    raw_input = state.get("target_input")
    if not raw_input:
        return
    material_s = str(raw_input)
    spot = best_resting_ask_cents(world, MaterialId(material_s))
    if spot is None or spot <= 0:
        return
    bid_price = max(2, (int(spot) * (10_000 - CONSOLIDATOR_FORWARD_DISCOUNT_BPS)) // 10_000)
    # Find a settler with surplus stock of the target input.
    candidates: list[tuple[str, int]] = []
    for p in world.parties:
        ps = str(p)
        if not ps.startswith("settler_"):
            continue
        stock = world.inventory.stock.get(p, {}) or {}
        qty = int(stock.get(MaterialId(material_s), 0))
        if qty < SETTLER_SURPLUS_MIN_UNITS:
            continue
        candidates.append((ps, qty))
    if not candidates:
        return
    candidates.sort(key=lambda x: (-x[1], x[0]))
    rng = world.rng(f"consolidator_forward:{world.tick}")
    pick = candidates[rng.randrange(min(3, len(candidates)))]
    seller_id = PartyId(pick[0])
    delivery = int(world.tick) + CONSOLIDATOR_FORWARD_HORIZON_TICKS
    prop = propose_forward_contract(
        world,
        seller_id,
        CONSOLIDATOR_PARTY_ID,
        MaterialId(material_s),
        CONSOLIDATOR_FORWARD_QTY,
        int(bid_price),
        delivery,
    )
    if not prop.get("ok"):
        return
    cid = str(prop.get("contract_id", ""))
    # Consolidator (as buyer) accepts immediately, locking the deposit on the seller.
    r = accept_forward_contract(world, CONSOLIDATOR_PARTY_ID, cid)
    if not r.get("ok"):
        log_event(
            world,
            "forward_proposal_skipped",
            f"Consolidator forward {cid} could not be accepted: {r.get('reason')}",
            contract_id=cid,
            reason=str(r.get("reason", "")),
        )

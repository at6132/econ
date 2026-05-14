"""Phase 9H — Order-book sanity / agent re-quote dampener.

NPC agents (Tier 1 / Tier 2 / Tier 3) used to cancel and re-post their
resting limit orders on a fixed cadence even when the market hadn't
moved. That churn:

- Reset time-priority on the book (player orders sat behind freshly
  reposted NPC quotes).
- Generated tons of cancel events that buried real market signal in
  ``world.event_log``.
- Cost zero — there was no transaction cost discouraging frivolous
  cancels.

This module exposes a tiny stateless policy:

- ``should_requote(world, party, material, side, intended_price)`` — the
  decision function. Returns ``True`` only if either (a) the agent has
  no resting orders on this (material, side), or (b) the intended price
  has moved by ``REQUOTE_MIN_DELTA_CENTS`` AND the cooldown
  ``REQUOTE_COOLDOWN_TICKS`` has elapsed since the last re-quote.
- ``charge_cancel_fee(world, party, n)`` — small flat per-cancel fee
  that drains to ``system:reserve`` (think of it as exchange
  microfees). Fee is **optional**: callers pass through, and we silently
  skip when the agent can't pay so we never break a chain.
- ``record_requote(world, party, material, side, price)`` — stamp the
  party's re-quote ledger so the next cooldown is measured correctly.

State is stored in ``world.scenario_state["agent_quote_state"]`` as a
flat dict so it serializes naturally without new dataclasses. Key shape:
``"<party>|<material>|<side>"`` -> ``{"last_price": int, "last_tick":
int}``.
"""

from __future__ import annotations

from typing import Final, Literal

from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World


Side = Literal["bid", "ask"]


REQUOTE_COOLDOWN_TICKS: Final[int] = 60
"""1 game-hour cooldown between re-quotes for the same (party, material,
side). Production agents cycle on 18-24 tick cadences, so this still
lets them re-quote each cadence -- it just kills sub-hour churn."""

REQUOTE_MIN_DELTA_CENTS: Final[int] = 2
"""Intended price must differ from the last re-quote by at least this
much to justify a cancel-and-replace. A 1 cent jitter every cadence is
not a real edge -- it's just noise that resets time-priority."""

CANCEL_FEE_CENTS: Final[int] = 5
"""Per-cancel microfee (5 cents). Trivial for a real strategy, but
multiplies into a real cost for an agent that re-quotes 100 times a day
for no reason."""


def _state_key(party: PartyId, material: MaterialId, side: Side) -> str:
    return f"{party}|{material}|{side}"


def _agent_quote_state(world: World) -> dict[str, dict]:
    state = world.scenario_state.setdefault("agent_quote_state", {})
    return state  # type: ignore[return-value]


def _has_resting_order(
    world: World, party: PartyId, material: MaterialId, side: Side
) -> bool:
    key = str(material)
    if side == "ask":
        for o in world.market_asks_by_material.get(key, []):
            if o.party == party:
                return True
    else:
        for b in world.market_bids_by_material.get(key, []):
            if b.party == party:
                return True
    return False


def should_requote(
    world: World,
    party: PartyId,
    material: MaterialId,
    side: Side,
    intended_price_cents: int,
) -> bool:
    """Decide whether an NPC agent should cancel its resting orders and
    re-post at ``intended_price_cents``.

    Permissive when the agent has nothing on the book; strict when it
    already has a quote that hasn't materially moved.
    """
    if intended_price_cents <= 0:
        return False
    # No resting orders -> always allowed to post.
    if not _has_resting_order(world, party, material, side):
        return True
    state = _agent_quote_state(world).get(_state_key(party, material, side))
    if state is None:
        # No prior memory but there *is* a resting order — let it ride.
        # The agent will re-record on the next post.
        return False
    elapsed = int(world.tick) - int(state.get("last_tick", 0))
    if elapsed < REQUOTE_COOLDOWN_TICKS:
        return False
    last_px = int(state.get("last_price", 0))
    if abs(intended_price_cents - last_px) < REQUOTE_MIN_DELTA_CENTS:
        return False
    return True


def record_requote(
    world: World,
    party: PartyId,
    material: MaterialId,
    side: Side,
    price_cents: int,
) -> None:
    """Stamp the dampener state so the next cooldown is measured from now."""
    state = _agent_quote_state(world)
    state[_state_key(party, material, side)] = {
        "last_price": int(price_cents),
        "last_tick": int(world.tick),
    }


def charge_cancel_fee(world: World, party: PartyId, cancels_count: int) -> int:
    """Charge ``CANCEL_FEE_CENTS`` per cancel to ``party``, draining to
    ``system:reserve``. Returns the cents actually charged.

    Silent no-op if the agent can't cover the fee (we don't want to
    break the agent's strategy chain over a 5-cent fee).
    """
    if cancels_count <= 0:
        return 0
    fee = cancels_count * CANCEL_FEE_CENTS
    src = party_cash_account(party)
    if world.ledger.balance(src) < fee:
        return 0
    tr = world.ledger.transfer(
        debit=src,
        credit=system_reserve_account(),
        amount_cents=fee,
    )
    if isinstance(tr, MoneyErr):
        return 0
    return fee


__all__ = [
    "Side",
    "REQUOTE_COOLDOWN_TICKS",
    "REQUOTE_MIN_DELTA_CENTS",
    "CANCEL_FEE_CENTS",
    "should_requote",
    "record_requote",
    "charge_cancel_fee",
]

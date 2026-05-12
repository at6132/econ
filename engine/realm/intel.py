"""Market information access (Law 6) — extended history is a paid subscription."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.time_scale import TICKS_PER_GAME_DAY
from realm.world import World

# ~4 in-game hours of best-bid/ask snapshots at one snapshot per tick.
FREE_MARKET_HISTORY_TICKS = 240

# Without an active subscription, ``world_public_dict`` only exposes the last N snapshots.
MARKET_INTEL_FEE_CENTS = 25_000  # $250.00
MARKET_INTEL_EXTEND_TICKS = 7 * TICKS_PER_GAME_DAY  # one week of in-game minutes


def purchase_market_intel(world: World, party: PartyId) -> dict:
    """
    Pay ``MARKET_INTEL_FEE_CENTS``; extend ``market_intel_expires_tick`` so the client receives
    full ``market_history`` until the new expiry (measured in simulation ticks).
    """
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < MARKET_INTEL_FEE_CENTS:
        return {"ok": False, "reason": "insufficient cash for market intel"}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=MARKET_INTEL_FEE_CENTS,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    base = max(world.market_intel_expires_tick, world.tick)
    world.market_intel_expires_tick = base + MARKET_INTEL_EXTEND_TICKS
    log_event(
        world,
        "market_intel",
        f"{party} purchased market analytics through tick {world.market_intel_expires_tick} "
        f"(${MARKET_INTEL_FEE_CENTS / 100:.2f})",
        party=str(party),
        expires_tick=world.market_intel_expires_tick,
        fee_cents=MARKET_INTEL_FEE_CENTS,
    )
    return {
        "ok": True,
        "expires_tick": world.market_intel_expires_tick,
        "fee_cents": MARKET_INTEL_FEE_CENTS,
    }

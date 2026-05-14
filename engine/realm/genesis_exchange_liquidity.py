"""Genesis clearinghouse — markup-priced backstop that withdraws when real producers exist.

The exchange is the **buyer/seller of last resort**, never the default source.
Daily, it tallies distinct non-exchange sellers per material over the trailing
``EXCHANGE_SELLER_WINDOW_TICKS``:

* **≥ ``EXCHANGE_WITHDRAW_MIN_DISTINCT_SELLERS``** distinct sellers ⇒ flip ``managed[mat]``
  to ``False``. The exchange stops topping up new clips; it sells from a finite
  ``EXCHANGE_UNMANAGED_RESERVE_UNITS``-pool that does **not** restock until
  ``managed`` is restored.
* **< ``EXCHANGE_RESTORE_MAX_DISTINCT_SELLERS + 1``** distinct sellers for
  ``EXCHANGE_RESTORE_LOW_DAYS`` consecutive days ⇒ flip back to ``True`` and
  refill the reserve.

Ask price is anchored every ``EXCHANGE_PRICE_REFRESH_TICKS`` to the volume-
weighted average of recent fills (held flat if no fills). On bootstrap the
anchor is the static markup baseline.

State is persisted in ``world.scenario_state["exchange"]``:
``{"managed": dict[str,bool], "reserve_unmanaged": dict[str,int],
   "low_seller_streak": dict[str,int], "last_listed_tick": dict[str,int],
   "last_window_check_tick": int, "last_price_refresh_tick": int,
   "price": dict[str,int], "fills": list[dict]}``
"""

from __future__ import annotations

from typing import Any

from realm.genesis_pricing import (
    EXCHANGE_LISTING_MAX_QTY_PER_CLIP,
    EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK,
    EXCHANGE_PRICE_REFRESH_TICKS,
    EXCHANGE_RELIST_COOLDOWN_TICKS,
    EXCHANGE_RESTORE_LOW_DAYS,
    EXCHANGE_RESTORE_MAX_DISTINCT_SELLERS,
    EXCHANGE_SELLER_WINDOW_TICKS,
    EXCHANGE_UNMANAGED_RESERVE_UNITS,
    EXCHANGE_WITHDRAW_MIN_DISTINCT_SELLERS,
    _baseline_exchange_ask_cents,
    exchange_ask_cents,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.markets import place_sell_order
from realm.world import World

_GENESIS_EXCHANGE = PartyId("genesis_exchange")


GENESIS_EXCHANGE_PARTY_ID = _GENESIS_EXCHANGE


def exchange_price_for_party(
    base_price_cents: int, party_reputation: dict | None
) -> int:
    """Reputation-adjusted exchange price (Sprint 5 — Phase C.5).

    The base order-book price is the same for everyone; this function
    returns the *effective* price the named party would pay when buying
    from the genesis exchange. The diff is settled post-fill as a rebate
    (or surcharge) between the buyer and the exchange.

    Tiers
    -----
    * ``honored \u2265 25``: 8% discount
    * ``honored \u2265 10``: 5% discount
    * ``breached > honored``: 5% premium
    * otherwise: unchanged
    """
    base = int(base_price_cents)
    rep = party_reputation or {}
    honored = int(rep.get("honored", 0))
    breached = int(rep.get("breached", 0))
    if honored >= 25:
        return int(base * 92 // 100)
    if honored >= 10:
        return int(base * 95 // 100)
    if breached > honored:
        return int(base * 105 // 100)
    return base


def apply_exchange_reputation_adjustment(
    world: World, buyer: PartyId, fill_qty: int, fill_unit_price_cents: int
) -> None:
    """Settle the rebate/surcharge after an exchange-seller fill.

    Called from the market matcher when the resting ask was the genesis
    exchange. Conservation is preserved: any rebate is paid from the
    exchange account, any surcharge is sent to it.
    """
    base_total = int(fill_qty) * int(fill_unit_price_cents)
    rep = world.reputation.get(str(buyer))
    effective_unit = exchange_price_for_party(int(fill_unit_price_cents), rep)
    effective_total = int(fill_qty) * effective_unit
    diff = base_total - effective_total
    if diff == 0:
        return
    buyer_acct = party_cash_account(buyer)
    ex_acct = party_cash_account(_GENESIS_EXCHANGE)
    if diff > 0:
        world.ledger.transfer(
            debit=ex_acct,
            credit=buyer_acct,
            amount_cents=int(diff),
        )
    else:
        magnitude = -diff
        if world.ledger.balance(buyer_acct) < magnitude:
            return
        world.ledger.transfer(
            debit=buyer_acct,
            credit=ex_acct,
            amount_cents=int(magnitude),
        )
_TICKS_PER_GAME_DAY = 1440

# Target backstop depth per material when no real seller is on the book.
# Price is derived from the markup-over-cost baseline in ``genesis_pricing``.
_STAPLES: tuple[tuple[MaterialId, int], ...] = (
    (MaterialId("coal"), 48),
    (MaterialId("electricity"), 56),
    (MaterialId("grain"), 48),
    (MaterialId("timber"), 36),
    (MaterialId("lumber"), 500),
    (MaterialId("brick"), 500),
    (MaterialId("stone"), 500),
    (MaterialId("pick_axe"), 200),
    (MaterialId("mining_pick"), 200),
    (MaterialId("spade"), 200),
    (MaterialId("hand_saw"), 100),
)


def _ex_state(world: World) -> dict[str, Any]:
    """Get-or-create the ``scenario_state["exchange"]`` blob with all sub-maps."""
    st = world.scenario_state.setdefault("exchange", {})
    st.setdefault("managed", {})
    st.setdefault("reserve_unmanaged", {})
    st.setdefault("low_seller_streak", {})
    st.setdefault("last_listed_tick", {})
    st.setdefault("price", {})
    st.setdefault("fills", [])
    st.setdefault("last_window_check_tick", -1)
    st.setdefault("last_price_refresh_tick", -1)
    return st


def _staple_keys() -> list[str]:
    return [str(m) for m, _ in _STAPLES]


def ensure_exchange_state_initialised(world: World) -> None:
    """Seed ``managed=True`` and the static ask price for every staple at bootstrap."""
    if world.scenario_id != "genesis":
        return
    st = _ex_state(world)
    managed = st["managed"]
    price = st["price"]
    for mat_str in _staple_keys():
        managed.setdefault(mat_str, True)
        price.setdefault(mat_str, _baseline_exchange_ask_cents(MaterialId(mat_str)))


def record_market_fill(
    world: World, material: MaterialId, qty: int, price_per_unit_cents: int, seller: PartyId
) -> None:
    """Capture realised trade prices for the exchange's lagging anchor.

    Only fills *not* sold by the exchange itself contribute to the rolling
    average (the exchange shouldn't anchor on its own quotes — feedback loop).
    Excess history is trimmed to a single refresh window.
    """
    if world.scenario_id != "genesis":
        return
    if seller == _GENESIS_EXCHANGE:
        return
    if qty <= 0 or price_per_unit_cents <= 0:
        return
    st = _ex_state(world)
    fills: list[dict] = st["fills"]
    fills.append(
        {
            "tick": int(world.tick),
            "material": str(material),
            "qty": int(qty),
            "price": int(price_per_unit_cents),
        }
    )
    horizon = int(world.tick) - 2 * EXCHANGE_PRICE_REFRESH_TICKS
    if fills and fills[0]["tick"] < horizon:
        # Trim opportunistically; bounded since we only call this on fills.
        st["fills"] = [f for f in fills if int(f["tick"]) >= horizon]


def _distinct_non_exchange_sellers_window(world: World, material: str) -> int:
    """Count distinct non-exchange parties that filed a market_list for ``material``
    in the past ``EXCHANGE_SELLER_WINDOW_TICKS``."""
    cutoff = int(world.tick) - EXCHANGE_SELLER_WINDOW_TICKS
    seen: set[str] = set()
    # event_log gets trimmed to ~1200 entries; for a 7-day window we may miss
    # older listings. Tally also from currently-resting asks (they're recent
    # by definition since they haven't filled yet).
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < cutoff:
            break
        if ev.get("kind") != "market_list":
            continue
        if str(ev.get("material") or "") != material:
            # Some log_event call sites may not set "material"; the message
            # contains the material id but parsing it is brittle. Skip.
            continue
        party = str(ev.get("party") or "")
        if not party or party == str(_GENESIS_EXCHANGE):
            continue
        seen.add(party)
    for ask in world.market_asks_by_material.get(material, []):
        party = str(ask.party)
        if party == str(_GENESIS_EXCHANGE):
            continue
        seen.add(party)
    return len(seen)


def _maybe_run_daily_managed_check(world: World) -> None:
    """Once per game-day, decide managed/unmanaged per material."""
    st = _ex_state(world)
    last = int(st.get("last_window_check_tick", -1))
    # Run on the very first call, then once every ``_TICKS_PER_GAME_DAY``.
    if last >= 0 and int(world.tick) - last < _TICKS_PER_GAME_DAY:
        return
    st["last_window_check_tick"] = int(world.tick)
    managed = st["managed"]
    reserves = st["reserve_unmanaged"]
    streak = st["low_seller_streak"]
    for mat_str in _staple_keys():
        n_sellers = _distinct_non_exchange_sellers_window(world, mat_str)
        was_managed = bool(managed.get(mat_str, True))
        if was_managed:
            if n_sellers >= EXCHANGE_WITHDRAW_MIN_DISTINCT_SELLERS:
                managed[mat_str] = False
                reserves[mat_str] = EXCHANGE_UNMANAGED_RESERVE_UNITS
                streak[mat_str] = 0
            else:
                streak[mat_str] = 0
        else:
            if n_sellers <= EXCHANGE_RESTORE_MAX_DISTINCT_SELLERS:
                streak[mat_str] = int(streak.get(mat_str, 0)) + 1
                if streak[mat_str] >= EXCHANGE_RESTORE_LOW_DAYS:
                    managed[mat_str] = True
                    reserves[mat_str] = EXCHANGE_UNMANAGED_RESERVE_UNITS
                    streak[mat_str] = 0
            else:
                streak[mat_str] = 0


def _maybe_refresh_anchored_price(world: World) -> None:
    """Re-anchor the exchange ask off the volume-weighted recent fill average."""
    st = _ex_state(world)
    last = int(st.get("last_price_refresh_tick", -1))
    if last >= 0 and int(world.tick) - last < EXCHANGE_PRICE_REFRESH_TICKS:
        return
    st["last_price_refresh_tick"] = int(world.tick)
    cutoff = int(world.tick) - EXCHANGE_PRICE_REFRESH_TICKS
    bucket_qty: dict[str, int] = {}
    bucket_value: dict[str, int] = {}
    for f in st["fills"]:
        if int(f["tick"]) < cutoff:
            continue
        m = str(f["material"])
        q = int(f["qty"])
        p = int(f["price"])
        bucket_qty[m] = bucket_qty.get(m, 0) + q
        bucket_value[m] = bucket_value.get(m, 0) + q * p
    price_map: dict[str, int] = st["price"]
    for mat_str in _staple_keys():
        q = bucket_qty.get(mat_str, 0)
        if q <= 0:
            # No fills this window → hold last price.
            continue
        avg_real = bucket_value[mat_str] // q
        # Anchor at avg + a small markup so the exchange always stays the *more*
        # expensive option even after re-anchoring.
        tier_marked = (avg_real * 11_000) // 10_000  # +10% over average
        baseline = _baseline_exchange_ask_cents(MaterialId(mat_str))
        new_px = max(tier_marked, baseline)
        price_map[mat_str] = int(new_px)


def _exchange_can_list(world: World, mat_str: str) -> bool:
    """Withdrawal + cooldown + reserve gate. Returns True if exchange may post a new clip."""
    st = _ex_state(world)
    managed = st["managed"]
    is_managed = bool(managed.get(mat_str, True))
    last_listed = int(st["last_listed_tick"].get(mat_str, -10_000))
    if int(world.tick) - last_listed < EXCHANGE_RELIST_COOLDOWN_TICKS:
        return False
    if not is_managed:
        if int(st["reserve_unmanaged"].get(mat_str, 0)) <= 0:
            return False
    return True


def _consume_reserve_for_listing(world: World, mat_str: str, qty: int) -> None:
    st = _ex_state(world)
    if bool(st["managed"].get(mat_str, True)):
        return
    cur = int(st["reserve_unmanaged"].get(mat_str, 0))
    st["reserve_unmanaged"][mat_str] = max(0, cur - int(qty))


def tick_genesis_exchange_quoting(world: World) -> None:
    """
    Top-of-tick liquidity backstop with finite-reserve withdrawal.

    The clearinghouse only relists when **non-exchange** resting ask depth is below
    ``EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK`` AND the per-material managed/reserve
    gates allow it. When real producers have the book covered, the exchange
    withdraws and the cheapest settler clip clears first (price-time priority).
    """
    if world.scenario_id != "genesis" or _GENESIS_EXCHANGE not in world.parties:
        return
    ensure_exchange_state_initialised(world)
    _maybe_run_daily_managed_check(world)
    _maybe_refresh_anchored_price(world)

    for mid, _target_units in _STAPLES:
        mat_str = str(mid)
        asks = world.market_asks_by_material.get(mat_str, [])
        ex_on_book = 0
        non_ex_on_book = 0
        for o in asks:
            visible = int(o.qty) + int(o.iceberg_hidden_qty)
            if o.party == _GENESIS_EXCHANGE:
                ex_on_book += visible
            else:
                non_ex_on_book += visible
        if non_ex_on_book >= EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK:
            continue
        if not _exchange_can_list(world, mat_str):
            continue
        inv = world.inventory.qty(_GENESIS_EXCHANGE, mid)
        if inv <= 0:
            continue
        # Per-clip cap: smaller than legacy 90/200 so settlers can outpace.
        clip = min(EXCHANGE_LISTING_MAX_QTY_PER_CLIP, inv)
        # In unmanaged mode, never list more than the reserve allows.
        st = _ex_state(world)
        if not bool(st["managed"].get(mat_str, True)):
            clip = min(clip, int(st["reserve_unmanaged"].get(mat_str, 0)))
            if clip <= 0:
                continue
        if clip <= 0:
            continue
        price = exchange_ask_cents(mid, world=world)
        result = place_sell_order(world, _GENESIS_EXCHANGE, mid, clip, price)
        if result.get("ok"):
            _consume_reserve_for_listing(world, mat_str, clip)
            st["last_listed_tick"][mat_str] = int(world.tick)

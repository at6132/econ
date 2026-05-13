"""Sprint 1 / Phase A — exchange withdrawal, finite reserves, markup pricing."""

from __future__ import annotations

from realm.genesis_exchange_liquidity import (
    _GENESIS_EXCHANGE,
    _ex_state,
    tick_genesis_exchange_quoting,
)
from realm.genesis_pricing import (
    EXCHANGE_RESTORE_LOW_DAYS,
    EXCHANGE_UNMANAGED_RESERVE_UNITS,
    EXCHANGE_WITHDRAW_MIN_DISTINCT_SELLERS,
    _baseline_exchange_ask_cents,
    exchange_ask_cents,
    hub_max_bid_cents,
    producer_cost_basis_cents,
)
from realm.ids import MaterialId, PartyId
from realm.markets import place_sell_order
from realm.world import bootstrap_genesis

_TICKS_PER_GAME_DAY = 1440


def _ledger_total(w) -> int:
    return w.ledger.total_cents()


def _fresh_genesis():
    return bootstrap_genesis(seed=7, settler_count=20, grid_width=24, grid_height=18)


def _seed_party_cash(w, party: PartyId, cents: int) -> None:
    from realm.ledger import party_cash_account, system_reserve_account

    w.ledger.ensure_account(party_cash_account(party))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=cents,
    )


def test_exchange_managed_by_default() -> None:
    """On bootstrap every tracked staple starts ``managed=True`` with the static markup price."""
    w = _fresh_genesis()
    st = _ex_state(w)
    assert st["managed"], "managed map must be seeded"
    for mat, flag in st["managed"].items():
        assert flag is True, f"{mat} should start managed=True (got {flag!r})"
    for mat, px in st["price"].items():
        assert px > 0, f"{mat} must have a positive seed price"
        assert px == _baseline_exchange_ask_cents(MaterialId(mat))


def test_exchange_price_is_above_cost_basis() -> None:
    """For every staple, the exchange ask must sit ≥ 1.20× the producer cost basis.

    Cost basis is computed from input fair values + half-labor share. The exchange
    is the *most expensive* legal source — settlers must always have headroom.
    """
    w = _fresh_genesis()
    for mat_str in ["coal", "timber", "iron_ingot", "brick", "copper_wire", "electricity"]:
        mat = MaterialId(mat_str)
        ask = exchange_ask_cents(mat, world=w)
        cost = producer_cost_basis_cents(mat)
        if cost is None or cost <= 0:
            continue
        assert ask >= int(cost * 1.20), (
            f"{mat_str}: ask={ask}¢ but cost_basis={cost}¢ (ratio "
            f"{ask / cost:.2f} < 1.20)"
        )


def test_hub_bid_cap_is_below_exchange() -> None:
    """Hub willingness-to-pay = exchange_ask × 0.92 — discount that lets settlers undercut."""
    w = _fresh_genesis()
    for mat_str in ["coal", "grain", "timber", "iron_ingot"]:
        mat = MaterialId(mat_str)
        cap = hub_max_bid_cents(mat)
        ask = exchange_ask_cents(mat, world=w)
        assert cap < ask, f"{mat_str}: hub cap {cap}¢ should be below ask {ask}¢"
        assert cap >= int(ask * 0.90), f"{mat_str}: hub cap {cap}¢ too low vs ask {ask}¢"


def test_exchange_withdraws_with_distinct_producers() -> None:
    """Three distinct non-exchange listings within the 7-day window → managed=False after daily check."""
    w = _fresh_genesis()
    starting_total = _ledger_total(w)
    coal = MaterialId("coal")
    # Three fresh seller parties post coal listings (small qty each).
    for i in range(EXCHANGE_WITHDRAW_MIN_DISTINCT_SELLERS):
        p = PartyId(f"settler_{i:03d}")
        w.parties.add(p)
        w.reputation.setdefault(str(p), {"honored": 0, "breached": 0})
        _seed_party_cash(w, p, 100_000)
        w.inventory.add(p, coal, 25)
        r = place_sell_order(w, p, coal, 5, 50)
        assert r.get("ok"), r
    # Force the daily-check to run by advancing scenario_state's recorded last-check.
    # Also push ``last_listed_tick`` forward so the same-tick top-up doesn't drain the
    # freshly-initialised reserve before we observe it.
    st = _ex_state(w)
    st["last_window_check_tick"] = -1
    st["last_listed_tick"]["coal"] = int(w.tick)
    tick_genesis_exchange_quoting(w)
    assert st["managed"]["coal"] is False, "coal should withdraw with 3 distinct sellers"
    assert st["reserve_unmanaged"]["coal"] == EXCHANGE_UNMANAGED_RESERVE_UNITS, (
        "reserve must initialise to the unmanaged cap on the managed→unmanaged transition"
    )
    # Ledger conservation: only registration fees + listing fees move (no creation).
    assert _ledger_total(w) == starting_total


def test_exchange_finite_reserve_when_unmanaged() -> None:
    """Once unmanaged, the exchange tops up only up to the per-material reserve cap."""
    w = _fresh_genesis()
    coal = MaterialId("coal")
    # Force unmanaged with empty reserve.
    st = _ex_state(w)
    st["managed"]["coal"] = False
    st["reserve_unmanaged"]["coal"] = 7  # less than per-clip cap
    st["last_listed_tick"]["coal"] = w.tick - 1_000  # ignore cooldown
    # Clear any standing exchange asks so the quoting loop has room to top up.
    asks = w.market_asks_by_material.get("coal", [])
    keep = [a for a in asks if a.party != _GENESIS_EXCHANGE]
    if keep:
        w.market_asks_by_material["coal"] = keep
    else:
        w.market_asks_by_material.pop("coal", None)
    tick_genesis_exchange_quoting(w)
    new_asks = w.market_asks_by_material.get("coal", [])
    ex_clips = [a for a in new_asks if a.party == _GENESIS_EXCHANGE]
    assert ex_clips, "exchange should post one clip out of remaining reserve"
    assert sum(int(a.qty) for a in ex_clips) <= 7
    # Reserve drained — subsequent tick produces nothing more.
    after = int(_ex_state(w)["reserve_unmanaged"]["coal"])
    assert after <= 7 - 1
    # Drain to zero, then any further tick must not add.
    st["reserve_unmanaged"]["coal"] = 0
    before_count = sum(int(a.qty) for a in w.market_asks_by_material.get("coal", []))
    st["last_listed_tick"]["coal"] = w.tick - 1_000
    tick_genesis_exchange_quoting(w)
    after_count = sum(int(a.qty) for a in w.market_asks_by_material.get("coal", []))
    assert after_count <= before_count, "no new exchange listing once reserve is 0"


def test_exchange_restores_after_consecutive_low_days() -> None:
    """Unmanaged → managed transition requires ``EXCHANGE_RESTORE_LOW_DAYS`` low-seller game-days."""
    w = _fresh_genesis()
    st = _ex_state(w)
    coal = "coal"
    st["managed"][coal] = False
    st["reserve_unmanaged"][coal] = 0
    st["low_seller_streak"][coal] = 0
    # Drive ``_maybe_run_daily_managed_check`` forward N days with 0 distinct non-exchange sellers.
    for day in range(EXCHANGE_RESTORE_LOW_DAYS):
        st["last_window_check_tick"] = w.tick - _TICKS_PER_GAME_DAY - 1
        tick_genesis_exchange_quoting(w)
    assert st["managed"][coal] is True, "coal should restore to managed after low-seller days"
    assert st["reserve_unmanaged"][coal] == EXCHANGE_UNMANAGED_RESERVE_UNITS


def test_exchange_relist_cooldown() -> None:
    """Per-material 30-tick relist cooldown prevents immediate refill of a depleted clip."""
    w = _fresh_genesis()
    st = _ex_state(w)
    st["last_listed_tick"]["coal"] = int(w.tick)
    initial = len(w.market_asks_by_material.get("coal", []))
    # Immediate next tick: still in cooldown — no new exchange listings.
    tick_genesis_exchange_quoting(w)
    after = len(w.market_asks_by_material.get("coal", []))
    assert after <= initial + 0


def test_no_money_creation_through_phase_a() -> None:
    """End-to-end conservation: tick the genesis exchange repeatedly, ledger stays constant."""
    w = _fresh_genesis()
    starting_total = _ledger_total(w)
    for _ in range(50):
        tick_genesis_exchange_quoting(w)
        w.tick += 1
    assert _ledger_total(w) == starting_total

"""Genesis price model — clearinghouse spread, settler cost-basis, depth-gated backstop."""

from __future__ import annotations

from realm.genesis_exchange_liquidity import tick_genesis_exchange_quoting
from realm.genesis_pricing import (
    EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK,
    exchange_ask_cents,
    fair_value_cents,
    settler_ask_cents,
    settler_cost_basis_cents,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.markets import place_sell_order
from realm.world import bootstrap_genesis


def test_exchange_ask_sits_above_fair_value() -> None:
    """Clearinghouse quotes a positive spread — never sits on the fair-value print itself."""
    for mid_s in ("coal", "electricity", "grain", "timber"):
        mid = MaterialId(mid_s)
        fv = fair_value_cents(mid)
        ex = exchange_ask_cents(mid)
        assert fv is not None
        assert ex > fv, f"{mid_s}: exchange {ex} must be above fair {fv}"


def test_settler_cost_basis_uses_input_only_for_coal() -> None:
    """``mine_coal``: 2 electricity (60¢ each) / 2 coal = 60¢ per coal (labor is overhead, excluded)."""
    cb = settler_cost_basis_cents(MaterialId("coal"))
    assert cb == 60


def test_settler_ask_undercuts_exchange_for_staples() -> None:
    """Settler ask is strictly below the clearinghouse quote so they win price-time."""
    w = bootstrap_genesis(seed=1, grid_width=6, grid_height=5, settler_count=2)
    for mid_s in ("coal", "electricity", "grain", "timber"):
        mid = MaterialId(mid_s)
        s_ask = settler_ask_cents(w, mid)
        ex = exchange_ask_cents(mid)
        cost = settler_cost_basis_cents(mid)
        assert s_ask < ex, f"{mid_s}: settler {s_ask} should beat exchange {ex}"
        if cost is not None:
            assert s_ask >= cost, f"{mid_s}: settler {s_ask} should clear input cost {cost}"


def test_settler_ask_lifts_bid_when_above_floor() -> None:
    """If a buyer is bidding above floor, settler lifts that bid (+1¢) capped by ceiling."""
    w = bootstrap_genesis(seed=2, grid_width=4, grid_height=4, settler_count=0)
    mid = MaterialId("coal")
    ceiling = exchange_ask_cents(mid) - 2
    px = settler_ask_cents(w, mid, best_resting_bid=63)
    assert px == 64  # 63 + 1, between floor and ceiling
    px2 = settler_ask_cents(w, mid, best_resting_bid=10_000)
    assert px2 == ceiling


def test_settler_ask_respects_fair_value_floor_on_downstream_goods() -> None:
    """Timber input cost (≈26¢/unit) is below 85% of fair (96 × 0.85 = 82¢) — fair-value floor applies."""
    w = bootstrap_genesis(seed=5, grid_width=4, grid_height=4, settler_count=0)
    mid = MaterialId("timber")
    ask = settler_ask_cents(w, mid)
    fv = fair_value_cents(mid)
    assert fv is not None
    assert ask >= (fv * 85) // 100, f"timber ask {ask} fell below fair-value floor 0.85×{fv}"
    assert ask < exchange_ask_cents(mid)


def _clear_book(w, mid: MaterialId) -> None:
    """Test helper — wipe asks for ``mid`` (cancellation would fail on bootstrap inventory caps)."""
    key = str(mid)
    if key in w.market_asks_by_material:
        w.market_asks_by_material[key] = []


def test_exchange_withdraws_when_settler_depth_present() -> None:
    """Above the watermark of non-exchange asks, the clearinghouse adds no clips this tick."""
    w = bootstrap_genesis(seed=3, grid_width=6, grid_height=5, settler_count=1)
    mid = MaterialId("coal")
    _clear_book(w, mid)
    seller = PartyId("settler_001")
    ad = w.inventory.add(seller, mid, EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK + 4)
    assert not isinstance(ad, MatterErr)
    s_ask = settler_ask_cents(w, mid)
    pr = place_sell_order(
        w, seller, mid, EXCHANGE_NON_EXCHANGE_DEPTH_WATERMARK + 4, s_ask
    )
    assert pr["ok"] is True, pr
    tick_genesis_exchange_quoting(w)
    ex_clips = [
        o for o in w.market_asks_by_material.get(str(mid), [])
        if o.party == PartyId("genesis_exchange")
    ]
    assert ex_clips == [], "exchange should not add clips when settlers cover demand"


def test_exchange_tops_up_when_book_is_thin() -> None:
    """Below the watermark the exchange relists from inventory at its spreaded ask."""
    w = bootstrap_genesis(seed=4, grid_width=6, grid_height=5, settler_count=0)
    mid = MaterialId("coal")
    _clear_book(w, mid)
    tick_genesis_exchange_quoting(w)
    asks = w.market_asks_by_material.get(str(mid), [])
    ex_asks = [o for o in asks if o.party == PartyId("genesis_exchange")]
    assert ex_asks, "thin book → exchange must relist"
    assert all(o.price_per_unit_cents == exchange_ask_cents(mid) for o in ex_asks)


def test_bootstrap_seeds_exchange_at_spreaded_ask() -> None:
    """Cold-start seed prices match steady-state quotes — no mid-tick price discontinuity."""
    w = bootstrap_genesis(seed=6, grid_width=6, grid_height=5, settler_count=0)
    for mid_s in ("coal", "electricity", "grain", "timber"):
        mid = MaterialId(mid_s)
        asks = w.market_asks_by_material.get(str(mid), [])
        ex_asks = [o for o in asks if o.party == PartyId("genesis_exchange")]
        assert ex_asks
        for o in ex_asks:
            assert o.price_per_unit_cents == exchange_ask_cents(mid)

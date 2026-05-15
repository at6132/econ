"""Regional comparative advantage (bootstrap + analytics)."""

from __future__ import annotations

from realm.core.ids import PlotId
from realm.economy.analytics import purchase_analytics_product
from realm.world import bootstrap_genesis
from realm.world.regional_advantage import (
    ADVANTAGE_CATEGORIES,
    generate_regional_advantages,
    qualitative_band,
    regional_advantage_modifier,
    seed_regional_advantages,
)


def test_regional_advantages_generated_per_landmass() -> None:
    w = bootstrap_genesis(seed=1401, grid_width=48, grid_height=36, settler_count=4)
    seed_regional_advantages(w)
    ids = {int(v) for v in w.landmass_id.values() if int(v) >= 0}
    assert ids
    n = max(ids) + 1
    for lm in range(n):
        adv = w.regional_advantages.get(lm)
        assert adv is not None
        for cat in ADVANTAGE_CATEGORIES:
            assert cat in adv


def test_modifier_in_range() -> None:
    adv = generate_regional_advantages(99, 4)
    for _lm, cats in adv.items():
        for _c, m in cats.items():
            assert 0.8 <= m <= 1.3


def test_mining_advantage_increases_output() -> None:
    w = bootstrap_genesis(seed=1402, grid_width=48, grid_height=36, settler_count=4)
    seed_regional_advantages(w)
    pid = next(iter(w.plots))
    lm = int(w.landmass_id.get(str(pid), -1))
    if lm < 0:
        return
    w.regional_advantages[lm] = {c: 1.0 for c in ADVANTAGE_CATEGORIES}
    w.regional_advantages[lm]["mining"] = 1.3
    assert regional_advantage_modifier(w, PlotId(str(pid)), "mine_coal") == 1.3


def test_agriculture_disadvantage_reduces_output() -> None:
    w = bootstrap_genesis(seed=1403, grid_width=48, grid_height=36, settler_count=4)
    seed_regional_advantages(w)
    pid = next(iter(w.plots))
    lm = int(w.landmass_id.get(str(pid), -1))
    if lm < 0:
        return
    w.regional_advantages[lm] = {c: 1.0 for c in ADVANTAGE_CATEGORIES}
    w.regional_advantages[lm]["agriculture"] = 0.8
    assert regional_advantage_modifier(w, PlotId(str(pid)), "grow_grain") == 0.8


def test_analytics_product_returns_qualitative_band() -> None:
    w = bootstrap_genesis(seed=1404, grid_width=48, grid_height=36, settler_count=4)
    seed_regional_advantages(w)
    lm = next(iter(w.regional_advantages))
    w.regional_advantages[int(lm)]["mining"] = 1.25
    from realm.core.ids import PartyId

    r = purchase_analytics_product(
        w,
        PartyId("player"),
        "regional_efficiency",
        {"landmass_id": int(lm), "category": "mining"},
    )
    assert r["ok"] is True
    band = r["data"]["band"]
    assert band in ("Excellent", "Good", "Average", "Poor")
    assert band == qualitative_band(1.25)


def test_same_seed_same_advantages() -> None:
    a = generate_regional_advantages(42, 5)
    b = generate_regional_advantages(42, 5)
    assert a == b

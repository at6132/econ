"""Tests for rolling trade-volume index."""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.economy.trade_volume_index import (
    match_seller_volumes_by_material_window,
    party_trade_share_bps,
    trade_volume_by_material_window,
    trade_volume_by_party_for_material,
)
from realm.world import bootstrap_genesis


def test_match_seller_volumes_by_material_window() -> None:
    w = bootstrap_genesis(seed=2, grid_width=12, grid_height=12, settler_count=2)
    w.tick = 3000
    log_event(
        w,
        "market_match",
        "fill",
        seller="settler_001",
        material="coal",
        qty=10,
    )
    log_event(
        w,
        "market_buy",
        "agg",
        seller="settler_002",
        material="coal",
        filled=99,
    )
    vols = match_seller_volumes_by_material_window(w, window_ticks=1440)
    assert vols.get("coal", {}).get("settler_001") == 10
    assert vols.get("coal", {}).get("settler_002") is None


def test_trade_volume_index_from_log_event() -> None:
    w = bootstrap_genesis(seed=1, grid_width=12, grid_height=12, settler_count=2)
    w.tick = 5000
    log_event(
        w,
        "market_match",
        "fill",
        seller="settler_001",
        material="coal",
        qty=10,
    )
    log_event(
        w,
        "market_match",
        "fill",
        seller="kessler_industrial",
        material="coal",
        qty=30,
    )
    vols = trade_volume_by_material_window(w, window_ticks=1440)
    assert vols.get("coal") == 40
    per = trade_volume_by_party_for_material(w, "coal", window_ticks=1440)
    assert per.get("settler_001") == 10
    assert per.get("kessler_industrial") == 30
    share = party_trade_share_bps(
        w, "kessler_industrial", "coal", window_ticks=1440
    )
    assert share == 7500  # 30/40

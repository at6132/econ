"""Genesis full-blob round-trip (Phase 2 pre-UI persistence gate)."""

from __future__ import annotations

from realm.api.serialization import dumps_json, loads_json
from realm.world.tick import advance_tick
from realm.world.world import bootstrap_genesis


def test_full_world_roundtrip_genesis() -> None:
    w1 = bootstrap_genesis(seed=42, grid_width=20, grid_height=18, settler_count=10)
    for _ in range(100):
        advance_tick(w1)

    ledger_total = w1.ledger.total_cents()
    n_laborers = len(w1.laborers)
    n_businesses = len(w1.businesses)
    n_roads = len(w1.road_segments)
    n_feed = len(w1.world_feed_log)
    lm_type = w1.landmass_type
    route_ops = w1.scenario_state.get("route_operators")

    w2 = loads_json(dumps_json(w1))

    assert w2.tick == w1.tick
    assert w2.ledger.total_cents() == ledger_total
    assert len(w2.laborers) == n_laborers
    assert len(w2.businesses) == n_businesses
    assert len(w2.road_segments) == n_roads
    assert len(w2.world_feed_log) == n_feed
    assert w2.landmass_type == lm_type
    assert w2.scenario_state.get("route_operators") == route_ops

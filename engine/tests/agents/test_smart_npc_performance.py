"""Performance budget for genesis settler intelligence."""

from __future__ import annotations

import os
import time


def test_smart_npc_tick_budget() -> None:
    """100 ticks with 20 settlers must complete in < 10ms/tick average."""
    os.environ["REALM_LLM_DISABLE"] = "1"
    from realm.world.world import bootstrap_genesis
    from realm.world.tick import advance_tick

    w = bootstrap_genesis(seed=42, settler_count=20)
    for _ in range(10):
        advance_tick(w)
    t0 = time.perf_counter()
    for _ in range(100):
        advance_tick(w)
    elapsed = time.perf_counter() - t0
    avg_ms = elapsed / 100 * 1000
    assert avg_ms < 10.0, f"tick too slow: {avg_ms:.1f}ms/tick"

"""Quick economy diagnostic — configurable days."""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

SEED = 42
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick

t0 = time.time()
w = bootstrap_genesis(
    seed=SEED, grid_width=48, grid_height=36,
    settler_count=8, settler_spawn_cap=50,
)
start_cents = int(w.ledger.total_cents())
ec: Counter[str] = Counter()
seen: set[int] = set()

def drain() -> None:
    for e in w.event_log:
        eid = id(e)
        if eid in seen:
            continue
        seen.add(eid)
        ec[str(e.get("kind") or "")] += 1

drain()
for day in range(1, DAYS + 1):
    for _ in range(TICKS_PER_GAME_DAY):
        advance_tick(w)
    drain()
    if day % 10 == 0 or day == DAYS:
        settlers = sum(1 for p in w.parties if str(p).startswith("settler_"))
        print(
            f"d{day:3d} pop={len(w.laborers):3d} settlers={settlers:2d} "
            f"matches={ec['market_match']} sell_fill={ec['market_sell_fill']} "
            f"prod={ec['production_done']} hire={ec['laborer_hired']} "
            f"quit={ec['wage_unpaid_quit']} paid={ec['laborer_wage_paid']} "
            f"stores={ec['store_purchase']}"
        )

elapsed = time.time() - t0
print(f"\n{elapsed:.1f}s | delta={int(w.ledger.total_cents()) - start_cents}")
print("top events:", ec.most_common(15))
ss = w.scenario_state
print(f"companies={len(ss.get('companies') or {})} contracts={len(ss.get('bilateral_contracts') or [])}")

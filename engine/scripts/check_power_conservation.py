"""One-off: 2 game-days of genesis ticks + ledger conservation."""
from __future__ import annotations

import os
import sys

os.environ["REALM_LLM_DISABLE"] = "1"
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from realm.infrastructure.power_grid import compute_grid_regions
from realm.world.tick import advance_tick
from realm.world.world import bootstrap_genesis


def main() -> None:
    w = bootstrap_genesis(seed=42, settler_count=10)
    start = w.ledger.total_cents()
    for _ in range(2880):
        advance_tick(w)
    end = w.ledger.total_cents()
    ok = end == start
    print(f"Conservation: {'OK' if ok else f'VIOLATED: {end - start}c'}")
    regions = compute_grid_regions(w)
    print(f"Grid regions: {len(regions)}")
    print(
        f"Regions with generators: "
        f"{sum(1 for r in regions.values() if r.capacity_per_day > 0)}"
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

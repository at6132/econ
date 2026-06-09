"""Quick labor headcount check at day 365 (seed 42, solo grid)."""
from __future__ import annotations

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick

SEED = 42
DAYS = 120
MIN_LABORERS = 55


def main() -> None:
    w = bootstrap_genesis(seed=SEED, grid_width=48, grid_height=36, settler_count=8, settler_spawn_cap=50)
    boot = len(w.laborers)
    while w.tick < DAYS * TICKS_PER_GAME_DAY:
        advance_tick(w)
    final = len(w.laborers)
    print(f"seed={SEED} days={DAYS} laborers {boot} -> {final}")
    if final < MIN_LABORERS:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

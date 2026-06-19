"""Profile advance_tick cost at a given game-day checkpoint.

Usage (from engine/):
    python scripts/profile_tick.py --day 120 --ticks 50
"""
from __future__ import annotations

import argparse
import cProfile
import pstats
import io
import time

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=int, default=120)
    ap.add_argument("--ticks", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    w = bootstrap_genesis(
        seed=args.seed, grid_width=48, grid_height=36, settler_count=8, settler_spawn_cap=50
    )
    target = args.day * TICKS_PER_GAME_DAY
    t0 = time.perf_counter()
    while w.tick < target:
        advance_tick(w)
    boot = time.perf_counter() - t0
    print(f"Reached day {args.day} in {boot:.1f}s | event_log={len(w.event_log)} "
          f"fob={len(w.market_fob_pickups)} labor={len(w.laborers)}")

    prof = cProfile.Profile()
    prof.enable()
    t1 = time.perf_counter()
    for _ in range(args.ticks):
        advance_tick(w)
    wall = time.perf_counter() - t1
    prof.disable()
    print(f"Profiled {args.ticks} ticks in {wall:.3f}s ({wall / args.ticks * 1000:.1f} ms/tick)")

    buf = io.StringIO()
    ps = pstats.Stats(prof, stream=buf).sort_stats("cumulative")
    ps.print_stats(35)
    print(buf.getvalue())


if __name__ == "__main__":
    main()

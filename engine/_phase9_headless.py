"""Phase 9 — headless realism probe.

Boot a genesis world and run 60 game-days of real ``advance_tick``,
recording each tick's event_log and select world state. Output goes to
``_phase9_run.log`` (one JSON object per game-day) and a final summary.

Run from engine/ with `python _phase9_headless.py`. Will take several
minutes — leave it running and read the log file when done.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick

OUT = Path("_phase9_run.log")
SUMMARY = Path("_phase9_summary.json")
GAME_DAYS = 30

t0 = time.time()
world = bootstrap_genesis(
    seed=42,
    grid_width=48,
    grid_height=36,
    settler_count=8,
)
boot_t = time.time() - t0
print(f"bootstrap: {boot_t:.1f}s  plots={len(world.plots)}  laborers={len(world.laborers)}  parties={len(world.parties)}")

starting_total = world.ledger.total_cents()
seen_event_ids: set[int] = set()
event_counts: Counter[str] = Counter()
samples: dict[str, list[dict]] = {}  # kind -> first 3 samples

OUT.write_text("")
log = OUT.open("a", encoding="utf-8")

def _scan() -> None:
    """Drain new events, count kinds, sample first 3 of each."""
    for e in world.event_log:
        eid = id(e)
        if eid in seen_event_ids:
            continue
        seen_event_ids.add(eid)
        kind = str(e.get("kind") or "")
        event_counts[kind] += 1
        bucket = samples.setdefault(kind, [])
        if len(bucket) < 3:
            bucket.append({k: v for k, v in e.items() if k not in ("message",)})
    if len(seen_event_ids) > 30_000:
        seen_event_ids.clear()
        seen_event_ids.update(id(e) for e in world.event_log)

_scan()

for day in range(GAME_DAYS):
    for _ in range(TICKS_PER_GAME_DAY):
        advance_tick(world)
    _scan()
    daily = {
        "day": day + 1,
        "tick": int(world.tick),
        "laborers_alive": len(world.laborers),
        "ledger_total_cents": int(world.ledger.total_cents()),
        "ledger_delta_from_start": int(world.ledger.total_cents()) - int(starting_total),
        "matter_units": int(world.inventory.total_units()),
        "towns": len(world.towns),
        "stores_built": sum(len(getattr(t, "store_plots", []) or []) for t in world.towns.values()),
        "in_transit_shipments": len(world.in_transit),
        "open_asks": sum(len(v) for v in world.market_asks_by_material.values()),
        "open_bids": sum(len(v) for v in world.market_bids_by_material.values()),
        "contracts_total": len(world.contracts),
        "world_events_active": len(getattr(world, "active_world_events", []) or []) if hasattr(world, "active_world_events") else 0,
    }
    log.write(json.dumps(daily) + "\n")
    log.flush()
    if (day + 1) % 5 == 0:
        elapsed = time.time() - t0
        print(f"day {day + 1:3d}/{GAME_DAYS}  laborers={daily['laborers_alive']:4d}  towns={daily['towns']}  cents_delta={daily['ledger_delta_from_start']:+d}  ({elapsed:.0f}s)")

log.close()
elapsed = time.time() - t0
print(f"DONE in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
print(f"matter_delta = {world.inventory.total_units() - 0}  (start=?, end={world.inventory.total_units()})")
print(f"ledger_delta = {world.ledger.total_cents() - starting_total} (conservation should be 0)")

SUMMARY.write_text(json.dumps({
    "game_days": GAME_DAYS,
    "elapsed_seconds": round(elapsed, 1),
    "final_laborers": len(world.laborers),
    "final_towns": len(world.towns),
    "ledger_start": int(starting_total),
    "ledger_end": int(world.ledger.total_cents()),
    "ledger_delta": int(world.ledger.total_cents()) - int(starting_total),
    "event_counts": dict(event_counts.most_common()),
    "event_samples": samples,
}, indent=2))
print(f"summary written to {SUMMARY}")

"""
year_run.py — run the Realm economy for one full game-year (365 days)
and write a single compact JSON report you can send for analysis.

Usage:
    python year_run.py

Output:
    year_report.json  (~200KB, send this file for analysis)

Runtime: ~10 minutes. Grab a coffee.
"""
from __future__ import annotations

import json
import time
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SEED            = 42
GRID_W, GRID_H  = 48, 36
SETTLER_COUNT   = 8
SETTLER_CAP     = 50
GAME_DAYS       = 365
OUT             = Path("year_report.json")

MATS = [
    "grain","coal","timber","lumber","iron_ore","iron_ingot",
    "brick","stone","smoked_fish","fish","clay","charcoal",
    "copper_ore","flour","bread","rope","slag",
]

INTERESTING = {
    "laborer_born","laborer_retired","laborer_poached",
    "labor_unrest_start","labor_unrest_end","laborer_trained",
    "genesis_settler_spawn",
    "company_formed","acquisition_complete",
    "contract_signed","contract_fulfilled","contract_breached",
    "market_corner","cartel_formed","cartel_broken",
    "panic_sell","spec_position_closed",
    "plot_listed","plot_sold","island_dominance_declared",
    "patent_granted","era_unlocked",
    "bank_loan_issued","bank_loan_defaulted",
    "world_event_start","world_event_end",
    "season_change",
    "exchange_emergency",
    "npc_message",
    "market_ddp_failed",
    "building_placed","home_builder_started",
}

# ── Bootstrap ─────────────────────────────────────────────────────────────────
print("=== Realm Year Run ===")
print(f"Seed {SEED} | {GRID_W}x{GRID_H} grid | {SETTLER_COUNT} settlers -> cap {SETTLER_CAP}")
print(f"Running {GAME_DAYS} game-days... (ETA ~10 min)\n")

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.seasons import current_season
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick

t0 = time.time()
w = bootstrap_genesis(
    seed=SEED, grid_width=GRID_W, grid_height=GRID_H,
    settler_count=SETTLER_COUNT, settler_spawn_cap=SETTLER_CAP,
)
boot_t = time.time() - t0
starting_cents = int(w.ledger.total_cents())

print(f"Boot {boot_t:.1f}s | laborers={len(w.laborers)} towns={len(w.towns)} parties={len(w.parties)}\n")
print(f"{'Day':>4} {'Season':>6} {'Pop':>4} {'Towns':>5} {'Settlers':>8} "
      f"{'Asks':>5} {'Bids':>4} {'Matches':>7} "
      f"{'Coal':>7} {'Grain':>7} {'Timber':>7} | Notes")
print("-" * 95)

# ── State ─────────────────────────────────────────────────────────────────────
_drain_cursor: int = 0
ec: Counter[str] = Counter()
narrative: list[dict] = []
price_hist: dict[str, list[float | None]] = {m: [] for m in MATS}
bid_hist:   dict[str, list[float | None]] = {m: [] for m in MATS}
daily_rows: list[dict] = []
match_total = 0
prod_total = 0
prev_season = ""

def _drain() -> None:
    global match_total, prod_total, _drain_cursor
    log = w.event_log
    while _drain_cursor < len(log):
        e = log[_drain_cursor]
        _drain_cursor += 1
        k = str(e.get("kind") or "")
        ec[k] += 1
        if k == "market_match":
            match_total += 1
        if k in INTERESTING:
            narrative.append({
                "day":  int(w.tick) // TICKS_PER_GAME_DAY + 1,
                "kind": k,
                "party": str(e.get("party") or ""),
                "msg":  str(e.get("message") or "")[:150],
            })
    _refresh_production_total()

def _refresh_production_total() -> None:
    global prod_total
    ops = w.scenario_state.get("settler_ops_completed") or {}
    prod_total = sum(int(v) for v in ops.values())

def _best_ask(m: str) -> float | None:
    orders = w.market_asks_by_material.get(m, [])
    if not orders:
        return None
    return min(o.price_per_unit_cents for o in orders) / 100

def _best_bid(m: str) -> float | None:
    orders = w.market_bids_by_material.get(m, [])
    if not orders:
        return None
    return max(o.max_price_per_unit_cents for o in orders) / 100

def _ss() -> dict:
    ss = w.scenario_state
    def L(k): return len(ss.get(k) or {})
    completed_research = sum(len(v) for v in (ss.get("research_completed") or {}).values())
    return {
        "companies":            L("companies"),
        "bilateral_contracts":  L("bilateral_contracts"),
        "bank_loans":           L("bank_loans"),
        "patents":              L("patents"),
        "active_research":      L("active_research"),
        "research_completed":   completed_research,
        "cartels":              L("cartels"),
        "spec_positions":       L("spec_positions"),
        "island_dominance":     L("island_dominance"),
        "plot_listings":        L("plot_listings"),
        "labor_unrest":         L("labor_unrest"),
        "exchange_restocks":    dict(ss.get("genesis_exchange_restocks") or {}),
        "current_era":          ss.get("current_global_era", "industrial"),
    }

def _laborer_stats() -> dict:
    laborers = list(w.laborers.values())
    if not laborers:
        return {"count": 0}
    h = [getattr(l, "health", 1.0) for l in laborers]
    s = [getattr(l, "savings_cents", 0) for l in laborers]
    skills = sum(1 for l in laborers if any(v > 0 for v in (getattr(l, "skill_levels", {}) or {}).values()))
    return {
        "count":       len(laborers),
        "avg_health":  round(sum(h) / len(h), 3),
        "avg_savings": int(sum(s) / len(s)),
        "skilled":     skills,
    }

_drain()

# ── Main loop ─────────────────────────────────────────────────────────────────
for day in range(1, GAME_DAYS + 1):
    for _ in range(TICKS_PER_GAME_DAY):
        advance_tick(w)
    _drain()

    season = current_season(w).value
    settlers = sum(1 for p in w.parties if str(p).startswith("settler_"))
    asks_n  = sum(len(v) for v in w.market_asks_by_material.values())
    bids_n  = sum(len(v) for v in w.market_bids_by_material.values())

    for m in MATS:
        price_hist[m].append(_best_ask(m))
        bid_hist[m].append(_best_bid(m))

    coal_a  = _best_ask("coal")
    grain_a = _best_ask("grain")
    timb_a  = _best_ask("timber")

    daily_rows.append({
        "day": day, "season": season,
        "laborers": len(w.laborers), "towns": len(w.towns),
        "settlers": settlers,
        "asks": asks_n, "bids": bids_n,
        "matches_total": match_total,
        "production_total": prod_total,
        "ledger_delta": int(w.ledger.total_cents()) - starting_cents,
        "prices": {m: _best_ask(m) for m in MATS},
        "bids_best": {m: _best_bid(m) for m in MATS},
        **_ss(),
    })

    # Console line every 10 days
    if day % 10 == 0 or season != prev_season:
        elapsed = time.time() - t0
        eta = (elapsed / day) * (GAME_DAYS - day)
        notes = []
        if season != prev_season and prev_season:
            notes.append(f"->{season}")
        prev_season = season

        # notable events since last print
        for kind in ("company_formed","world_event_start","era_unlocked","patent_granted"):
            n = ec[kind]
            if n:
                notes.append(f"{kind}={n}")

        def p(v): return f"${v:.2f}" if v is not None else "  --  "
        print(f"{day:>4} {season[:3]:>6} {len(w.laborers):>4} {len(w.towns):>5} "
              f"{settlers:>8} {asks_n:>5} {bids_n:>4} {match_total:>7} "
              f"{p(coal_a):>7} {p(grain_a):>7} {p(timb_a):>7} | "
              f"{', '.join(notes) if notes else ''}")
        sys.stdout.flush()

# ── Final report ──────────────────────────────────────────────────────────────
elapsed = time.time() - t0
print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f} min)")
print(f"Conservation check: ledger_delta = {int(w.ledger.total_cents()) - starting_cents}")

report = {
    "meta": {
        "seed": SEED, "grid": f"{GRID_W}x{GRID_H}",
        "settler_count": SETTLER_COUNT, "settler_cap": SETTLER_CAP,
        "game_days": GAME_DAYS, "elapsed_seconds": round(elapsed, 1),
        "boot_laborers": 76, "boot_towns": 4,
        "final_laborers": len(w.laborers),
        "final_towns": len(w.towns),
        "final_settlers": sum(1 for p in w.parties if str(p).startswith("settler_")),
        "final_parties": len(w.parties),
        "conservation_delta": int(w.ledger.total_cents()) - starting_cents,
        "total_market_matches": match_total,
        "total_settler_production": prod_total,
    },
    "event_counts": dict(ec.most_common()),
    "narrative": narrative,
    "daily": daily_rows,
    "price_history": price_hist,
    "bid_history": bid_hist,
    "final_state": {
        **_ss(),
        "labor": _laborer_stats(),
        "asks": {m: _best_ask(m) for m in MATS},
        "bids": {m: _best_bid(m) for m in MATS},
        "ask_depth": {m: sum(o.qty for o in w.market_asks_by_material.get(m, [])) for m in MATS},
        "bid_depth": {m: sum(o.qty for o in w.market_bids_by_material.get(m, [])) for m in MATS},
    },
}

OUT.write_text(json.dumps(report, indent=2))
size_kb = OUT.stat().st_size // 1024
print(f"Report written: {OUT}  ({size_kb} KB)")
print("Send year_report.json for analysis.")
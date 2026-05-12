#!/usr/bin/env python3
"""
Drive one in-game week (7 × 1440 ticks) as ``player`` via the Realm FastAPI surface only.

Requires a running engine (from repo ``engine/`` dir)::

    uvicorn realm.api:app --host 127.0.0.1 --port 8000

Then (defaults: Genesis, one week after strip-mine is operational)::

    python scripts/api_play_one_game_week.py
    python scripts/api_play_one_game_week.py --base http://127.0.0.1:8000 --seed 88

Uses ``POST /tick/batch`` so one week is not 10k sequential ``/tick`` HTTP calls.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKS_PER_GAME_DAY = 1440
TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY


def _req(
    base: str,
    method: str,
    path: str,
    *,
    query: dict[str, str | int] | None = None,
) -> tuple[int, dict | list | str | None]:
    q = urllib.parse.urlencode({k: str(v) for k, v in (query or {}).items()})
    url = f"{base.rstrip('/')}{path}"
    if q:
        url = f"{url}?{q}"
    r = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            raw = resp.read().decode()
            code = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        code = e.code
        try:
            return code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return code, {"detail": raw}
    try:
        return code, json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return code, raw


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default="http://127.0.0.1:8000", help="Engine origin (no /api/engine prefix)")
    p.add_argument("--seed", type=int, default=88)
    p.add_argument("--scenario", default="genesis", choices=("genesis", "frontier"))
    p.add_argument(
        "--week-ticks",
        type=int,
        default=TICKS_PER_GAME_WEEK,
        help=f"In-game ticks for the main batch (default {TICKS_PER_GAME_WEEK} = one week).",
    )
    args = p.parse_args()
    base: str = args.base
    build_ticks = 220
    week_ticks = int(args.week_ticks)
    if week_ticks < build_ticks + 1:
        print("--week-ticks must exceed construction buffer (default 220)", file=sys.stderr)
        return 1

    print("health check…", flush=True)
    code, _ = _req(base, "GET", "/health")
    if code != 200:
        print(f"Engine not reachable at {base} (GET /health -> {code}). Start uvicorn first.", file=sys.stderr)
        return 1

    print("reset…", flush=True)
    code, body = _req(base, "POST", "/dev/reset", query={"seed": args.seed, "scenario": args.scenario})
    if code != 200:
        print(f"reset failed: {code} {body}", file=sys.stderr)
        return 1
    print("reset:", body)

    print("/world (large on Genesis maps; may take a bit)…", flush=True)
    code, w = _req(base, "GET", "/world")
    if code != 200 or not isinstance(w, dict):
        print(f"/world failed: {code}", file=sys.stderr)
        return 1

    plots = w.get("plots") or []
    pick: str | None = None
    for pl in plots:
        if pl.get("terrain") == "mountain" and not pl.get("owner"):
            pick = str(pl["id"])
            break
    if pick is None:
        for pl in plots:
            if not pl.get("owner"):
                pick = str(pl["id"])
                break
    if pick is None:
        print("no unowned plot found", file=sys.stderr)
        return 1
    print("claim plot", pick)

    for path, msg in (
        (f"/plots/{urllib.parse.quote(pick, safe='')}/claim", "claim"),
        (f"/plots/{urllib.parse.quote(pick, safe='')}/survey", "survey"),
    ):
        code, body = _req(base, "POST", path, query={"party": "player"})
        if code != 200:
            print(f"{msg} failed: {code} {body}", file=sys.stderr)
            return 1
        print(msg, "ok")

    code, body = _req(
        base,
        "POST",
        f"/plots/{urllib.parse.quote(pick, safe='')}/build",
        query={"party": "player", "building_id": "strip_mine", "build_mode": "turnkey"},
    )
    if code != 200:
        print(f"build failed: {code} {body}", file=sys.stderr)
        return 1
    print("build strip_mine turnkey ok")

    # Construction window (strip mine contracted shell — see realm.time_scale.BUILD_CONTRACTED_TICKS).
    print(f"tick/batch construction ({build_ticks})…", flush=True)
    code, body = _req(base, "POST", "/tick/batch", query={"count": build_ticks})
    if code != 200:
        print(f"tick/batch construction failed: {code} {body}", file=sys.stderr)
        return 1
    print("construction batch:", body)

    code, w = _req(base, "GET", "/world")
    plot = next((x for x in (w or {}).get("plots", []) if x.get("id") == pick), None)
    rids = (plot or {}).get("recipe_ids") or []
    if "mine_coal" in rids:
        code, b2 = _req(
            base,
            "POST",
            "/market/buy",
            query={"party": "player", "material": "electricity", "max_qty": 40},
        )
        if code != 200:
            print(f"market/buy electricity: {code} {b2}", file=sys.stderr)
        else:
            print("bought electricity:", b2)
        code, b3 = _req(
            base,
            "POST",
            f"/plots/{urllib.parse.quote(pick, safe='')}/produce",
            query={"party": "player", "recipe_id": "mine_coal"},
        )
        if code != 200:
            print(f"produce mine_coal: {code} {b3}", file=sys.stderr)
        else:
            print("started mine_coal:", b3)
    else:
        print("mine_coal not on recipe_ids after build; skipping produce (terrain/subsurface). rids=", rids[:12])

    remaining = week_ticks - build_ticks
    print(f"tick/batch main sim ({remaining} ticks)…", flush=True)
    code, body = _req(base, "POST", "/tick/batch", query={"count": remaining})
    if code != 200:
        print(f"tick/batch week failed: {code} {body}", file=sys.stderr)
        return 1
    print("week batch:", body)

    code, w = _req(base, "GET", "/world")
    if isinstance(w, dict):
        tick = w.get("tick")
        inv = (w.get("inventory") or {}).get("player") or {}
        coal = inv.get("coal", 0)
        cash = (w.get("balances_cents") or {}).get("player", 0)
        print(f"end tick={tick} player coal={coal} player_cash_cents={cash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

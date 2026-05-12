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

    print("GET /world?compact=1 (plot hints + small payload)…", flush=True)
    code, w = _req(base, "GET", "/world", query={"compact": 1})
    if code != 200 or not isinstance(w, dict):
        print(f"/world?compact=1 failed: {code}", file=sys.stderr)
        return 1

    pick: str | None = w.get("claim_hint_mountain_plot_id") or w.get("claim_hint_any_plot_id")
    if pick is None:
        print("no claim hint in compact world", file=sys.stderr)
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

    code, w = _req(base, "GET", "/world", query={"compact": 1})
    if code != 200 or not isinstance(w, dict):
        print(f"/world?compact=1 after build failed: {code}", file=sys.stderr)
        return 1
    player_plots = (w.get("player") or {}).get("plots") or []
    plot = next((x for x in player_plots if x.get("id") == pick), None)
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

    code, w = _req(base, "GET", "/world", query={"compact": 1})
    if isinstance(w, dict):
        tick = w.get("tick")
        inv_top = (w.get("player") or {}).get("inventory_top") or []
        coal = next((x.get("qty", 0) for x in inv_top if x.get("material") == "coal"), 0)
        cash = (w.get("player") or {}).get("balance_cents", 0)
        print(f"end tick={tick} player coal={coal} player_cash_cents={cash}")
        print("compact tail (event_log_tail last 5):", flush=True)
        for ev in (w.get("event_log_tail") or [])[-5:]:
            print(" ", ev.get("tick"), ev.get("kind"), (ev.get("message") or "")[:100], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

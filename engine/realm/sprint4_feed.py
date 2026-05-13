"""Sprint 4 — Phase D.2/D.3: expanded world-feed triggers + weekly digest.

The existing ``genesis_feed_hooks`` covers ~10 event kinds (price-move, first
building, settler-hub-first, etc.). This module adds the rest of the 25+ trigger
catalogue requested by the sprint:

- Rank changes (player becoming top-3 / dropping out of top-5)
- Settler events (bankruptcies, settler count crossing milestones)
- Price/market events (10% daily moves, scarce materials, new commodities)
- Named agent observations (consolidator dominance, deep Tier-3 finds)
- Player milestones (first production, first forward, first report sale, net-worth)
- Energy/infrastructure (region power up/down)
- Weekly digest

All triggers are descriptive past-tense — never prescriptive. The player draws
their own conclusions.
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.markets import best_resting_ask_cents
from realm.world import World


_TICKS_PER_GAME_DAY: int = 1440
_WEEKLY_DIGEST_INTERVAL: int = 7 * 1440  # 10_080 ticks
_PRICE_MOVE_FAST_THRESHOLD: float = 0.10  # 10% per game-day
_SCARCITY_THRESHOLD_UNITS: int = 5
_SCARCITY_DAYS: int = 3
_NET_WORTH_MILESTONES: tuple[int, ...] = (5_000_000, 10_000_000, 25_000_000)
_SETTLER_POPULATION_MILESTONES: tuple[int, ...] = (100, 150, 200, 250, 300, 400, 500)

_TRACKED_MATERIALS: tuple[str, ...] = (
    "coal",
    "timber",
    "lumber",
    "grain",
    "electricity",
    "iron_ore",
    "iron_ingot",
    "copper_ore",
    "stone",
    "clay",
    "bread",
    "fish",
)


def _gst(world: World) -> dict[str, Any]:
    """Genesis scenario scratchpad bucket for feed-hook state."""
    st = world.scenario_state.setdefault("genesis", {})
    if not isinstance(st, dict):
        world.scenario_state["genesis"] = {}
        st = world.scenario_state["genesis"]
    return st


def _sprint4(world: World) -> dict[str, Any]:
    gst = _gst(world)
    s4 = gst.setdefault("sprint4_feed", {})
    if not isinstance(s4, dict):
        gst["sprint4_feed"] = {}
        s4 = gst["sprint4_feed"]
    s4.setdefault("daily_price_open_cents", {})
    s4.setdefault("scarcity_low_streak", {})
    s4.setdefault("traded_materials_ever", [])
    s4.setdefault("player_first_production_done", False)
    s4.setdefault("player_first_forward_done", False)
    s4.setdefault("player_first_report_sale_done", False)
    s4.setdefault("player_net_worth_milestones_hit", [])
    s4.setdefault("settler_population_milestones_hit", [])
    s4.setdefault("known_settler_bankruptcies", [])
    s4.setdefault("region_powered_state", {})
    s4.setdefault("rank_top3", {})
    s4.setdefault("rank_top5", {})
    return s4


def _settler_party_count(world: World) -> int:
    return sum(1 for p in world.parties if str(p).startswith("settler_"))


def _player_net_worth_cents(world: World) -> int:
    """Cash + a coarse mark-to-fair-value of held inventory + plot ownership.

    For milestone triggers we use cash + held inventory (best ask × qty for any
    material currently quoted on the book). Plot value isn't included — it's
    illiquid in v1.
    """
    from realm.ledger import party_cash_account

    player = PartyId("player")
    cash = world.ledger.balance(party_cash_account(player))
    stock = world.inventory.stock.get(player, {}) or {}
    total = cash
    for mid, qty in stock.items():
        if qty <= 0:
            continue
        px = best_resting_ask_cents(world, MaterialId(str(mid)))
        if px is None:
            continue
        total += int(qty) * int(px)
    return total


def _producer_volumes(
    world: World, window_ticks: int
) -> dict[str, dict[str, int]]:
    """``{material: {seller_party: qty}}`` over the window using match events."""
    cutoff = max(0, int(world.tick) - int(window_ticks))
    out: dict[str, dict[str, int]] = {}
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < cutoff:
            break
        if str(ev.get("kind", "")) != "market_match":
            continue
        material = str(ev.get("material") or "")
        seller = str(ev.get("seller") or "")
        if not material or not seller:
            continue
        qty = 0
        for k in ("qty", "filled", "fill_qty"):
            v = ev.get(k)
            if v is None:
                continue
            try:
                qty = int(v)
            except (TypeError, ValueError):
                qty = 0
            if qty > 0:
                break
        if qty <= 0:
            continue
        bucket = out.setdefault(material, {})
        bucket[seller] = bucket.get(seller, 0) + qty
    return out


def _label_party(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


# ─────────────────── individual trigger groups ───────────────────


def _scan_rank_changes(world: World) -> None:
    """Player crossing top-3 producer status or dropping out of top-5."""
    if world.scenario_id != "genesis":
        return
    s4 = _sprint4(world)
    vols = _producer_volumes(world, _TICKS_PER_GAME_DAY * 3)
    top3 = s4["rank_top3"]
    top5 = s4["rank_top5"]
    player_s = "player"
    for material, per_seller in vols.items():
        ranked = sorted(per_seller.items(), key=lambda kv: (-kv[1], kv[0]))
        sellers = [s for s, _ in ranked]
        if player_s not in sellers:
            continue
        pos = sellers.index(player_s) + 1
        was_top3 = bool(top3.get(material, False))
        was_top5 = bool(top5.get(material, False))
        is_top3 = pos <= 3 and per_seller[player_s] >= 10
        is_top5 = pos <= 5 and per_seller[player_s] >= 5
        if is_top3 and not was_top3:
            top3[material] = True
            log_event(
                world,
                "world_feed",
                f"You are now the {_ordinal(pos)} largest {material} producer.",
                feed_source="player_rank_top3",
                material=material,
                rank=pos,
                kind_tag="player_rank_top3",
            )
        if was_top5 and not is_top5:
            top5[material] = False
            log_event(
                world,
                "world_feed",
                f"Your {material} market share has declined — you are no longer a top-5 producer.",
                feed_source="player_rank_drop5",
                material=material,
                kind_tag="player_rank_drop5",
            )
        elif is_top5:
            top5[material] = True


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _scan_settler_bankruptcies(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    s4 = _sprint4(world)
    known: set[str] = set(s4.get("known_settler_bankruptcies", []))
    from realm.ledger import party_cash_account

    for p in world.parties:
        ps = str(p)
        if not ps.startswith("settler_"):
            continue
        if ps in known:
            continue
        balance = world.ledger.balance(party_cash_account(p))
        if balance < 0:
            known.add(ps)
            label = _label_party(world, p)
            log_event(
                world,
                "world_feed",
                f"A frontier settler folded this week ({label}). Their claims are unclaimed again.",
                feed_source="settler_bankruptcy",
                party=ps,
                kind_tag="settler_bankruptcy",
            )
    s4["known_settler_bankruptcies"] = sorted(known)


def _scan_settler_population_milestones(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    s4 = _sprint4(world)
    hit = list(s4.get("settler_population_milestones_hit", []))
    n = _settler_party_count(world)
    for m in _SETTLER_POPULATION_MILESTONES:
        if n >= m and m not in hit:
            hit.append(m)
            log_event(
                world,
                "world_feed",
                f"The frontier population reached {m} settlers.",
                feed_source="settler_population_milestone",
                settler_count=n,
                milestone=m,
                kind_tag="settler_population_milestone",
            )
    s4["settler_population_milestones_hit"] = hit


def _scan_daily_price_moves(world: World) -> None:
    """Per game-day price move > 10 % triggers a feed entry."""
    s4 = _sprint4(world)
    opens: dict[str, int] = dict(s4.get("daily_price_open_cents", {}))
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        # During the day, just update opens for any unseen materials.
        for mat_s in _TRACKED_MATERIALS:
            px = best_resting_ask_cents(world, MaterialId(mat_s))
            if px is not None and mat_s not in opens:
                opens[mat_s] = int(px)
        s4["daily_price_open_cents"] = opens
        return
    # Day-boundary: compare current to open, emit if >10% move, reset opens.
    for mat_s in _TRACKED_MATERIALS:
        cur = best_resting_ask_cents(world, MaterialId(mat_s))
        if cur is None:
            continue
        op = opens.get(mat_s)
        if op is not None and op > 0:
            pct = (cur - op) / float(op)
            if abs(pct) >= _PRICE_MOVE_FAST_THRESHOLD:
                direction = "spiked" if pct > 0 else "tumbled"
                log_event(
                    world,
                    "world_feed",
                    f"{mat_s.replace('_', ' ').title()} prices {direction} "
                    f"{abs(pct) * 100:.0f}% today — supply disruption.",
                    feed_source="price_spike",
                    material=mat_s,
                    move_pct=round(pct, 4),
                    kind_tag="price_spike",
                )
        opens[mat_s] = int(cur)
    s4["daily_price_open_cents"] = opens


def _scan_scarcity_streak(world: World) -> None:
    """Materials with < 5 ask-units on the book for ``_SCARCITY_DAYS`` consecutive days."""
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    s4 = _sprint4(world)
    streaks: dict[str, int] = dict(s4.get("scarcity_low_streak", {}))
    fired: set[str] = set(s4.get("scarcity_fired_today", []))
    materials_to_check = set(_TRACKED_MATERIALS)
    materials_to_check.update(map(str, world.market_asks_by_material.keys()))
    for mat in sorted(materials_to_check):
        asks = world.market_asks_by_material.get(mat, [])
        total = sum(int(o.qty) + int(o.iceberg_hidden_qty) for o in asks)
        if total < _SCARCITY_THRESHOLD_UNITS:
            streaks[mat] = streaks.get(mat, 0) + 1
            if streaks[mat] == _SCARCITY_DAYS and mat not in fired:
                fired.add(mat)
                log_event(
                    world,
                    "world_feed",
                    f"{mat.replace('_', ' ').title()} supply is critically low — "
                    f"only {total} units on market.",
                    feed_source="scarcity_streak",
                    material=mat,
                    units=total,
                    kind_tag="scarcity_streak",
                )
        else:
            streaks[mat] = 0
            if mat in fired:
                fired.discard(mat)
    s4["scarcity_low_streak"] = streaks
    s4["scarcity_fired_today"] = sorted(fired)


def _scan_new_commodity(world: World) -> None:
    """Emit one line the first time any new material appears on the ask book."""
    s4 = _sprint4(world)
    seen: set[str] = set(s4.get("traded_materials_ever", []))
    for mat in world.market_asks_by_material.keys():
        if str(mat) in seen:
            continue
        # Skip if the book is empty (cancelled clip leaves a stale empty key).
        if not world.market_asks_by_material.get(mat):
            continue
        seen.add(str(mat))
        log_event(
            world,
            "world_feed",
            f"A new commodity appeared on the eastern exchange: {str(mat).replace('_', ' ')}.",
            feed_source="new_commodity",
            material=str(mat),
            kind_tag="new_commodity",
        )
    s4["traded_materials_ever"] = sorted(seen)


def _scan_deep_survey_tier3(world: World) -> None:
    """Mirror the deep_survey_find event onto a region-anonymised headline.

    The base ``deep_survey`` hook fires ``world_feed`` directly per plot. Here
    we also emit a region-coloured note once per game-day if any Tier-3 grade
    was found in that region since the previous scan.
    """
    if world.scenario_id != "genesis":
        return
    s4 = _sprint4(world)
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    from realm.regions import _world_bounds, region_for_coords

    w, h = _world_bounds(world)
    already = set(s4.get("deep_survey_regions_seen", []))
    for plot in world.plots.values():
        if not getattr(plot, "deep_surveyed", False):
            continue
        notable = any(
            getattr(plot.subsurface, f, 0.0) >= 0.10
            for f in ("platinum_grade", "oil_shale_grade", "rare_earth_grade")
        )
        if not notable:
            continue
        region = region_for_coords(plot.x, plot.y, w, h)
        if region in already:
            continue
        already.add(region)
        log_event(
            world,
            "world_feed",
            f"Deep geological activity reported in region {region} — unusual finds.",
            feed_source="deep_survey_region",
            region_id=region,
            kind_tag="deep_survey_region",
        )
    s4["deep_survey_regions_seen"] = sorted(already)


def _scan_player_milestones(world: World) -> None:
    s4 = _sprint4(world)
    player = PartyId("player")
    if not s4.get("player_first_production_done"):
        for run in world.active_production:
            if run.party == player:
                s4["player_first_production_done"] = True
                log_event(
                    world,
                    "world_feed",
                    "Your first production run completed.",
                    feed_source="player_first_production",
                    kind_tag="player_first_production",
                )
                break
    if not s4.get("player_first_forward_done"):
        for c in world.contracts:
            if (
                str(c.get("kind", "")) == "forward_contract"
                and str(c.get("seller", "")) == "player"
            ):
                s4["player_first_forward_done"] = True
                log_event(
                    world,
                    "world_feed",
                    "You committed to a forward delivery — your first.",
                    feed_source="player_first_forward",
                    kind_tag="player_first_forward",
                )
                break
    if not s4.get("player_first_report_sale_done"):
        for row in world.intel_listings:
            if (
                str(row.get("seller", "")) == "player"
                and str(row.get("status", "")) == "sold"
            ):
                s4["player_first_report_sale_done"] = True
                log_event(
                    world,
                    "world_feed",
                    "You sold market intelligence for the first time.",
                    feed_source="player_first_report_sale",
                    kind_tag="player_first_report_sale",
                )
                break
    # Net worth milestones.
    hit: list[int] = list(s4.get("player_net_worth_milestones_hit", []))
    nw = _player_net_worth_cents(world)
    for m in _NET_WORTH_MILESTONES:
        if nw >= m and m not in hit:
            hit.append(m)
            usd_k = m // 100 // 1000
            log_event(
                world,
                "world_feed",
                f"Net worth milestone: ${usd_k}K.",
                feed_source="player_net_worth",
                milestone_cents=m,
                kind_tag="player_net_worth",
            )
    s4["player_net_worth_milestones_hit"] = hit


def _scan_region_power_changes(world: World) -> None:
    """Emit when a region gains its first power_shed, or loses its last one."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    from realm.regions import _world_bounds, region_for_coords
    from realm.time_scale import building_operational

    s4 = _sprint4(world)
    prev: dict[str, int] = dict(s4.get("region_powered_state", {}))
    cur: dict[str, int] = {}
    w, h = _world_bounds(world)
    for b in world.plot_buildings:
        if str(b.get("building_id", "")) != "power_shed":
            continue
        if not building_operational(b, at_tick=int(world.tick)):
            continue
        plot_id_s = str(b.get("plot_id", ""))
        plot = next(
            (p for p in world.plots.values() if str(p.plot_id) == plot_id_s),
            None,
        )
        if plot is None:
            continue
        r = region_for_coords(plot.x, plot.y, w, h)
        cur[r] = cur.get(r, 0) + 1
    for region, count in cur.items():
        if count > 0 and prev.get(region, 0) == 0:
            log_event(
                world,
                "world_feed",
                f"Region {region} is now connected to power.",
                feed_source="region_power_up",
                region_id=region,
                kind_tag="region_power_up",
            )
    for region, prev_count in prev.items():
        if prev_count > 0 and cur.get(region, 0) == 0:
            # Count powered plot buildings that went offline.
            log_event(
                world,
                "world_feed",
                f"Region {region} has lost power — its last power_shed went offline.",
                feed_source="region_power_down",
                region_id=region,
                kind_tag="region_power_down",
            )
    s4["region_powered_state"] = cur


def _scan_consolidator_dominance(world: World) -> None:
    """Mirror Kessler's >30% weekly share onto a dedicated kind for the spec."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    try:
        from realm.genesis_consolidator import (
            CONSOLIDATOR_PARTY_ID,
            consolidator_market_share_bps,
        )
    except ImportError:
        return
    if CONSOLIDATOR_PARTY_ID not in world.parties:
        return
    s4 = _sprint4(world)
    fired: set[str] = set(s4.get("consolidator_dominance_seen", []))
    vols = _producer_volumes(world, 7 * _TICKS_PER_GAME_DAY)
    for material in vols.keys():
        share = consolidator_market_share_bps(world, MaterialId(material))
        if share < 3_000:
            continue
        if material in fired:
            continue
        fired.add(material)
        log_event(
            world,
            "world_feed",
            f"A large buyer absorbed significant {material} supply this week.",
            feed_source="consolidator_absorb",
            material=material,
            kind_tag="consolidator_absorb",
        )
    s4["consolidator_dominance_seen"] = sorted(fired)


# ─────────────────── Weekly digest ───────────────────


def _emit_weekly_digest(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    if int(world.tick) == 0:
        return
    if int(world.tick) % _WEEKLY_DIGEST_INTERVAL != 0:
        return
    week_no = int(world.tick) // _WEEKLY_DIGEST_INTERVAL
    vols_week = _producer_volumes(world, _WEEKLY_DIGEST_INTERVAL)
    total_vols = {mat: sum(per.values()) for mat, per in vols_week.items()}
    ranked_total = sorted(total_vols.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    s4 = _sprint4(world)
    # Largest producer per material (only top 3 by total volume).
    largest_lines: list[str] = []
    for material, _ in ranked_total:
        per = vols_week.get(material, {})
        if not per:
            continue
        producer, qty = max(per.items(), key=lambda kv: (kv[1], -ord(kv[0][0]) if kv[0] else 0))
        total = sum(per.values()) or 1
        share = qty * 100 // total
        largest_lines.append(
            f"{material}: {_label_party(world, PartyId(producer))} ({share}%)"
        )
    # Price movers — compare with last week's opens stored in scratch.
    prev_opens: dict[str, int] = dict(s4.get("weekly_price_opens", {}))
    cur_prices: dict[str, int] = {}
    movers: list[tuple[str, float]] = []
    for mat_s in _TRACKED_MATERIALS:
        cur = best_resting_ask_cents(world, MaterialId(mat_s))
        if cur is None:
            continue
        cur_prices[mat_s] = int(cur)
        po = prev_opens.get(mat_s)
        if po is None or po <= 0:
            continue
        pct = (cur - po) / float(po)
        if abs(pct) >= 0.05:
            movers.append((mat_s, pct))
    movers.sort(key=lambda x: -abs(x[1]))
    mover_text = ", ".join(
        f"{m} {'+' if p > 0 else ''}{p * 100:.0f}%" for m, p in movers[:3]
    ) or "no >5% moves"
    s4["weekly_price_opens"] = cur_prices
    # Population.
    settlers = _settler_party_count(world)
    claimed = sum(1 for pl in world.plots.values() if pl.owner is not None)
    top_lines = ", ".join(
        f"{m} ({total_vols.get(m, 0)} units)" for m, _ in ranked_total
    ) or "none"
    log_event(
        world,
        "world_feed",
        " | ".join(
            [
                f"WEEKLY DIGEST — Week {week_no}",
                f"Top 3 traded materials: {top_lines}",
                f"Biggest price movers: {mover_text}",
                f"Largest producers: {'; '.join(largest_lines) or 'none'}",
                f"Population: {settlers} settlers active, {claimed} plots claimed",
            ]
        ),
        feed_source="weekly_digest",
        kind_tag="weekly_digest",
        week=week_no,
        settler_count=settlers,
        plots_claimed=claimed,
    )


# ─────────────────── public entry point ───────────────────


def tick_sprint4_feed(world: World) -> None:
    """Per-tick scan of all Sprint-4 feed triggers (call after ``world.tick`` increments)."""
    _scan_new_commodity(world)
    _scan_settler_bankruptcies(world)
    _scan_player_milestones(world)
    _scan_settler_population_milestones(world)
    _scan_daily_price_moves(world)
    _scan_scarcity_streak(world)
    _scan_deep_survey_tier3(world)
    _scan_region_power_changes(world)
    _scan_consolidator_dominance(world)
    _scan_rank_changes(world)
    _emit_weekly_digest(world)

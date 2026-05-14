"""Curated Genesis digest headlines (``world_feed``) — hourly cadence for macro deltas.

Event-scale headlines (prices, Margaux, bankruptcies, milestones) live in
``realm.genesis_feed_hooks.tick_genesis_feed_tick_scan`` and related hooks.
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.markets import best_resting_ask_cents
from realm.plot_logistics import party_material_held
from realm.time_scale import legacy_scaled
from realm.world import World

# One digest per in-game hour at 1440 ticks/day (was incorrectly scaled to ~16 game-hours).
GENESIS_DIGEST_INTERVAL_TICKS = 60

_PLAYER = PartyId("player")


def _genesis_st(world: World) -> dict[str, Any]:
    st = world.scenario_state.setdefault("genesis", {})
    if not isinstance(st, dict):
        world.scenario_state["genesis"] = {}
        st = world.scenario_state["genesis"]
    return st


def _settler_party_count(world: World) -> int:
    return sum(1 for p in world.parties if str(p).startswith("settler_"))


def _settler_strip_mines(world: World) -> int:
    return sum(
        1
        for b in world.plot_buildings
        if b.get("building_id") == "strip_mine" and str(b.get("party", "")).startswith("settler_")
    )


def _player_strip_mines(world: World) -> int:
    return sum(
        1
        for b in world.plot_buildings
        if b.get("building_id") == "strip_mine" and b.get("party") == str(_PLAYER)
    )


def tick_genesis_world_feed(world: World) -> None:
    """Emit digest lines on a fixed cadence (in-game minutes); prefer deltas; pulse if quiet."""
    if world.scenario_id != "genesis":
        return
    interval = GENESIS_DIGEST_INTERVAL_TICKS
    # Runs from ``tick.advance_tick`` **after** ``world.tick += 1`` so cadence matches displayed clock.
    if world.tick % interval != 0:
        return
    gst = _genesis_st(world)
    prev: dict[str, Any] = dict(gst.get("digest_prev", {}) or {})

    sm = _settler_strip_mines(world)
    pm = _player_strip_mines(world)
    total_mines = sum(1 for b in world.plot_buildings if b.get("building_id") == "strip_mine")
    ty = sum(
        1
        for b in world.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "timber_yard"
    )
    gr = sum(
        1
        for b in world.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "grain_row"
    )

    coal_ask = best_resting_ask_cents(world, MaterialId("coal"))
    grain_ask = best_resting_ask_cents(world, MaterialId("grain"))
    elec_ask = best_resting_ask_cents(world, MaterialId("electricity"))

    headlines: list[str] = []

    n_settlers = _settler_party_count(world)
    if not prev:
        headlines.append(
            f"Genesis digest opened t{world.tick}: {n_settlers} settler parties; "
            f"{total_mines} strip-mines (settler {sm}, player {pm})."
        )
    prev_pop = int(prev.get("settler_count", n_settlers))
    if n_settlers != prev_pop:
        headlines.append(
            f"Frontier headcount: {prev_pop} → {n_settlers} settler parties "
            f"(spawns and exits net)."
        )

    d_mines = total_mines - int(prev.get("total_mines", 0))
    if d_mines != 0:
        headlines.append(
            f"Since last digest: strip-mine count {'+' if d_mines > 0 else ''}{d_mines} "
            f"(now {total_mines}: {sm} settler, {pm} yours; {ty} timber-yards, {gr} grain-rows among settlers)."
        )

    if coal_ask is None and world.tick >= legacy_scaled(40):
        streak = int(gst.get("coal_ask_empty_streak", 0)) + 1
        gst["coal_ask_empty_streak"] = streak
        if streak >= 2 and streak % 2 == 0:
            headlines.append(
                f"Coal book still empty for {streak * interval} ticks — check exchange relists and entrepreneur asks."
            )
    else:
        gst["coal_ask_empty_streak"] = 0

    pqcoal = party_material_held(world, _PLAYER, MaterialId("coal"))
    prev_pc = int(prev.get("player_coal", pqcoal))
    if pqcoal != prev_pc and world.tick >= legacy_scaled(20):
        headlines.append(
            f"Your coal (inventory + staged at your plots) moved {prev_pc} → {pqcoal} u "
            "(not counting open sell clips)."
        )

    if not headlines:
        nasks = sum(len(v) for v in world.market_asks_by_material.values())
        nbids = sum(len(v) for v in world.market_bids_by_material.values())
        headlines.append(
            f"Genesis pulse t{world.tick}: {nasks} ask rows, {nbids} bid rows; "
            f"coal best ask {coal_ask if coal_ask is not None else '—'}¢."
        )

    gst["digest_prev"] = {
        "settler_count": n_settlers,
        "total_mines": total_mines,
        "coal_ask": coal_ask,
        "grain_ask": grain_ask,
        "elec_ask": elec_ask,
        "player_coal": pqcoal,
        "tick": world.tick,
    }

    rng = world.rng(f"gen:digest_pick:{world.tick}")
    k = min(3, len(headlines))
    picks = rng.sample(range(len(headlines)), k=k) if len(headlines) > 3 else list(range(len(headlines)))
    parts = [headlines[i] for i in sorted(picks)]
    log_event(world, "world_feed", " ".join(parts))

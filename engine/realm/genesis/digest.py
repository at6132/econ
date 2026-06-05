"""Curated Genesis digest headlines (``world_feed``) — hourly cadence for macro deltas.

Event-scale headlines (prices, Margaux, bankruptcies, milestones) live in
``realm.genesis.feed_hooks.tick_genesis_feed_tick_scan`` and related hooks.
"""

from __future__ import annotations

from typing import Any

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId
from realm.economy.markets import best_resting_ask_cents
from realm.infrastructure.plot_logistics import party_material_held
from realm.core.time_scale import TICKS_PER_GAME_DAY, legacy_scaled
from realm.world import World

# One digest per in-game hour at 1440 ticks/day (was incorrectly scaled to ~16 game-hours).
GENESIS_DIGEST_INTERVAL_TICKS = 60
_DIGEST_EMIT_COOLDOWN_TICKS = 5 * TICKS_PER_GAME_DAY

_PLAYER = PartyId("player")


def _genesis_st(world: World) -> dict[str, Any]:
    st = world.scenario_state.setdefault("genesis", {})
    if not isinstance(st, dict):
        world.scenario_state["genesis"] = {}
        st = world.scenario_state["genesis"]
    return st


def digest_emit_allowed(world: World, message_key: str) -> bool:
    """True when ``message_key`` was not emitted within the last 5 game-days."""
    gst = _genesis_st(world)
    last_emit = gst.get("digest_last_emit", {})
    if not isinstance(last_emit, dict):
        return True
    last_tick = int(last_emit.get(message_key, 0))
    return world.tick - last_tick >= _DIGEST_EMIT_COOLDOWN_TICKS


def record_digest_emit(world: World, message_key: str) -> None:
    gst = _genesis_st(world)
    last_emit = gst.setdefault("digest_last_emit", {})
    if not isinstance(last_emit, dict):
        last_emit = {}
        gst["digest_last_emit"] = last_emit
    last_emit[message_key] = int(world.tick)


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

    headlines: list[tuple[str, str]] = []

    n_settlers = _settler_party_count(world)
    if not prev:
        headlines.append(
            (
                "digest_open",
                f"Genesis digest opened t{world.tick}: {n_settlers} settler parties; "
                f"{total_mines} strip-mines (settler {sm}, player {pm}).",
            )
        )
    prev_pop = int(prev.get("settler_count", n_settlers))
    if n_settlers != prev_pop:
        headlines.append(
            (
                "digest_headcount_delta",
                f"Frontier headcount: {prev_pop} → {n_settlers} settler parties "
                f"(spawns and exits net).",
            )
        )

    d_mines = total_mines - int(prev.get("total_mines", 0))
    if d_mines != 0:
        headlines.append(
            (
                "digest_mines_delta",
                f"Since last digest: strip-mine count {'+' if d_mines > 0 else ''}{d_mines} "
                f"(now {total_mines}: {sm} settler, {pm} yours; {ty} timber-yards, {gr} grain-rows among settlers).",
            )
        )

    if coal_ask is None and world.tick >= legacy_scaled(40):
        streak = int(gst.get("coal_ask_empty_streak", 0)) + 1
        gst["coal_ask_empty_streak"] = streak
        if streak >= 2 and streak % 2 == 0:
            headlines.append(
                (
                    "digest_coal_ask_empty",
                    f"Coal book still empty for {streak * interval} ticks — check exchange relists and entrepreneur asks.",
                )
            )
    else:
        gst["coal_ask_empty_streak"] = 0

    pqcoal = party_material_held(world, _PLAYER, MaterialId("coal"))
    prev_pc = int(prev.get("player_coal", pqcoal))
    if pqcoal != prev_pc and world.tick >= legacy_scaled(20):
        headlines.append(
            (
                "digest_player_coal_move",
                f"Your coal (inventory + staged at your plots) moved {prev_pc} → {pqcoal} u "
                "(not counting open sell clips).",
            )
        )

    if not headlines:
        nasks = sum(len(v) for v in world.market_asks_by_material.values())
        nbids = sum(len(v) for v in world.market_bids_by_material.values())
        headlines.append(
            (
                "digest_genesis_pulse",
                f"Genesis pulse t{world.tick}: {nasks} ask rows, {nbids} bid rows; "
                f"coal best ask {coal_ask if coal_ask is not None else '—'}¢.",
            )
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

    eligible = [(key, text) for key, text in headlines if digest_emit_allowed(world, key)]
    if not eligible:
        return

    rng = world.rng(f"gen:digest_pick:{world.tick}")
    k = min(3, len(eligible))
    picks = rng.sample(range(len(eligible)), k=k) if len(eligible) > 3 else list(range(len(eligible)))
    parts: list[str] = []
    for i in sorted(picks):
        key, text = eligible[i]
        parts.append(text)
        record_digest_emit(world, key)
    log_event(world, "world_feed", " ".join(parts))

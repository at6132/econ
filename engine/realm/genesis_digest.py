"""Curated Genesis digest headlines (``world_feed``) — delta-first, low churn."""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.markets import best_resting_ask_cents
from realm.plot_logistics import party_material_held
from realm.world import World

_PLAYER = PartyId("player")
_HUB_E = PartyId("pop_hub_e")
_HUB_W = PartyId("pop_hub_w")


def _genesis_st(world: World) -> dict[str, Any]:
    st = world.scenario_state.setdefault("genesis", {})
    if not isinstance(st, dict):
        world.scenario_state["genesis"] = {}
        st = world.scenario_state["genesis"]
    return st


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
    """Every ~16 ticks emit digest lines; prefer deltas; always emit a pulse so the feed never goes silent."""
    if world.scenario_id != "genesis":
        return
    if world.tick < 1 or world.tick % 16 != 0:
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

    d_mines = total_mines - int(prev.get("total_mines", 0))
    if d_mines != 0:
        headlines.append(
            f"Since last digest: strip-mine count {'+' if d_mines > 0 else ''}{d_mines} "
            f"(now {total_mines}: {sm} settler, {pm} yours; {ty} timber-yards, {gr} grain-rows among settlers)."
        )
    elif world.tick >= 16:
        headlines.append(
            f"Tick {world.tick}: settler workshop mix steady — {total_mines} strip-mines, "
            f"{ty} timber yards, {gr} grain rows (settler-only)."
        )

    for label, cur, key in (
        ("Coal", coal_ask, "coal_ask"),
        ("Grain", grain_ask, "grain_ask"),
        ("Electricity", elec_ask, "elec_ask"),
    ):
        old = prev.get(key)
        if cur is None and old is not None:
            headlines.append(f"{label} asks just went empty on the book (was {old}¢).")
        elif cur is not None and old is None:
            headlines.append(f"{label} asks returned at {cur}¢.")
        elif cur is not None and old is not None and cur != old:
            headlines.append(f"{label} best ask moved {old}¢ → {cur}¢.")

    if coal_ask is None and world.tick >= 40:
        streak = int(gst.get("coal_ask_empty_streak", 0)) + 1
        gst["coal_ask_empty_streak"] = streak
        if streak >= 2 and streak % 2 == 0:
            headlines.append(
                f"Coal book still empty for {streak * 16} ticks — check exchange relists and hub lifts."
            )
    else:
        gst["coal_ask_empty_streak"] = 0

    for hub, hlabel, mid in (
        (_HUB_E, "Eastern pop hub", MaterialId("grain")),
        (_HUB_W, "Western pop hub", MaterialId("grain")),
        (_HUB_E, "Eastern pop hub", MaterialId("coal")),
    ):
        if hub not in world.parties:
            continue
        q = world.inventory.qty(hub, mid)
        pq = int(prev.get(f"hubinv:{hub}:{mid}", q))
        if q != pq:
            headlines.append(f"{hlabel} {mid} stock {pq} → {q} u.")

    pqcoal = party_material_held(world, _PLAYER, MaterialId("coal"))
    prev_pc = int(prev.get("player_coal", pqcoal))
    if pqcoal != prev_pc and world.tick >= 20:
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
        "total_mines": total_mines,
        "coal_ask": coal_ask,
        "grain_ask": grain_ask,
        "elec_ask": elec_ask,
        "player_coal": pqcoal,
        "hubinv:pop_hub_e:grain": world.inventory.qty(_HUB_E, MaterialId("grain")),
        "hubinv:pop_hub_w:grain": world.inventory.qty(_HUB_W, MaterialId("grain")),
        "hubinv:pop_hub_e:coal": world.inventory.qty(_HUB_E, MaterialId("coal")),
        "tick": world.tick,
    }

    rng = world.rng(f"gen:digest_pick:{world.tick}")
    k = min(3, len(headlines))
    picks = rng.sample(range(len(headlines)), k=k) if len(headlines) > 3 else list(range(len(headlines)))
    parts = [headlines[i] for i in sorted(picks)]
    log_event(world, "world_feed", " ".join(parts))

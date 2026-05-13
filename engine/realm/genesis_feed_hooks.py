"""Genesis ``world_feed`` milestones — event-triggered headlines (not interval-only)."""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.markets import best_resting_ask_cents
from realm.time_scale import building_operational
from realm.world import World

_HUB_IDS = frozenset({"pop_hub_e", "pop_hub_w"})
_PRICE_MATERIALS: tuple[str, ...] = ("timber", "lumber", "coal", "grain", "electricity")
_PRICE_HEADLINE_COOLDOWN_TICKS = 120


def _gst(world: World) -> dict[str, Any]:
    st = world.scenario_state.setdefault("genesis", {})
    if not isinstance(st, dict):
        world.scenario_state["genesis"] = {}
        st = world.scenario_state["genesis"]
    return st


def mirror_margaux_line_to_world_feed(world: World, display_name: str, text: str) -> None:
    """Surface Margaux (and similar) NPC lines on the public feed as well as ``npc_messages``."""
    if world.scenario_id != "genesis":
        return
    log_event(
        world,
        "world_feed",
        f"{display_name} — {text}",
        feed_source="npc_mirror",
        from_party="llm_margaux",
    )


def note_genesis_bankruptcy_feed(world: World, party: PartyId) -> None:
    if world.scenario_id != "genesis":
        return
    label = world.party_display_names.get(str(party), str(party))
    log_event(
        world,
        "world_feed",
        f"{label} folded under cash strain — plots and orders cleared to the exchange.",
        feed_source="bankruptcy",
        party=str(party),
    )


def note_genesis_first_building_operational(world: World, party: PartyId, building_id: str) -> None:
    """First time this ``building_id`` is operational anywhere (construction just finished)."""
    if world.scenario_id != "genesis":
        return
    t = world.tick
    n = sum(
        1
        for b in world.plot_buildings
        if str(b.get("building_id", "")) == building_id and building_operational(b, at_tick=t)
    )
    if n != 1:
        return
    gst = _gst(world)
    done = gst.setdefault("feed_first_building_types", [])
    if not isinstance(done, list):
        done = []
        gst["feed_first_building_types"] = done
    if building_id in done:
        return
    done.append(building_id)
    gst["feed_first_building_types"] = list(done)
    who = "You" if str(party) == "player" else label_party(world, party)
    pretty = building_id.replace("_", " ")
    log_event(
        world,
        "world_feed",
        f"First {pretty} opened on the frontier — {who} (t{world.tick}).",
        feed_source="first_building",
        building_id=building_id,
        party=str(party),
    )


def label_party(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def note_genesis_hub_market_buy(
    world: World,
    *,
    buyer: PartyId,
    material: MaterialId,
    filled: int,
    sellers_csv: str,
) -> None:
    """Record first time a settler's ask is lifted by a population hub (aggressive buy)."""
    if world.scenario_id != "genesis" or filled <= 0:
        return
    if str(buyer) not in _HUB_IDS:
        return
    sellers = [s for s in sellers_csv.split(",") if s and s.startswith("settler_")]
    if not sellers:
        return
    gst = _gst(world)
    first_map = gst.setdefault("settler_first_hub_sale", {})
    if not isinstance(first_map, dict):
        first_map = {}
        gst["settler_first_hub_sale"] = first_map
    hub = str(buyer)
    for sid in sellers:
        key = f"{sid}|{hub}"
        if key in first_map:
            continue
        first_map[key] = world.tick
        nm = world.party_display_names.get(sid, sid)
        log_event(
            world,
            "world_feed",
            f"{nm} sold into {hub} for the first time ({material} ×{filled} this clip).",
            feed_source="settler_hub_first",
            seller=sid,
            buyer=hub,
            material=str(material),
        )


def _maybe_player_coal_board_headline(world: World, gst: dict[str, Any]) -> None:
    if gst.get("feed_player_coal_board"):
        return
    key = "coal"
    asks = world.market_asks_by_material.get(key, [])
    if not asks:
        return
    has_player = any(str(o.party) == "player" for o in asks)
    has_settler = any(str(o.party).startswith("settler_") for o in asks)
    has_ex = any(str(o.party) == "genesis_exchange" for o in asks)
    if has_player and not has_settler and has_ex:
        gst["feed_player_coal_board"] = True
        log_event(
            world,
            "world_feed",
            "You're listing coal while no settler has a resting ask — only you and the clearinghouse "
            "on that board right now.",
            feed_source="player_coal_board",
        )


def tick_genesis_feed_tick_scan(world: World) -> None:
    """Each tick: watch staple best-asks for large moves; occasional player-vs-board facts."""
    if world.scenario_id != "genesis":
        return
    gst = _gst(world)
    prev: dict[str, Any] = dict(gst.get("feed_price_prev", {}) or {})
    last_emit: dict[str, Any] = dict(gst.get("feed_px_last_emit_tick", {}) or {})
    for mat_s in _PRICE_MATERIALS:
        mid = MaterialId(mat_s)
        cur = best_resting_ask_cents(world, mid)
        old = prev.get(mat_s)
        prev[mat_s] = cur
        if old is None or cur is None:
            continue
        if old < 10:
            continue
        if cur == old:
            continue
        pct = abs(cur - old) / float(old)
        if pct < 0.05:
            continue
        lt = int(last_emit.get(mat_s, -1_000_000))
        if world.tick - lt < _PRICE_HEADLINE_COOLDOWN_TICKS:
            continue
        label = mat_s.replace("_", " ").title()
        log_event(
            world,
            "world_feed",
            f"{label} spot lifted on the book: {old}¢ → {cur}¢ ({pct * 100:.0f}% move).",
            feed_source="price_move",
            material=mat_s,
        )
        last_emit[mat_s] = world.tick
    gst["feed_price_prev"] = prev
    gst["feed_px_last_emit_tick"] = last_emit
    _maybe_player_coal_board_headline(world, gst)
    _emit_first_building_opened_this_tick(world)


def _emit_first_building_opened_this_tick(world: World) -> None:
    """Headline when a workshop type becomes operational for the first time in the world."""
    if world.scenario_id != "genesis":
        return
    t = world.tick
    for b in world.plot_buildings:
        c = b.get("completes_at_tick")
        if c is None:
            continue
        if int(c) != t:
            continue
        if not building_operational(b, at_tick=t):
            continue
        bid = str(b.get("building_id", ""))
        if not bid:
            continue
        ps = str(b.get("party", ""))
        party = PartyId(ps) if ps else PartyId("player")
        note_genesis_first_building_operational(world, party, bid)

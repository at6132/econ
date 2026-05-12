"""Curated Genesis digest headlines (``world_feed``) — state-driven, low churn."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.markets import best_resting_ask_cents
from realm.world import World

_PLAYER = PartyId("player")
_HUB_E = PartyId("pop_hub_e")
_HUB_W = PartyId("pop_hub_w")


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


def _max_settler_inventory(world: World, material: MaterialId) -> tuple[int, PartyId | None]:
    best = 0
    who: PartyId | None = None
    for p in world.parties:
        if not str(p).startswith("settler_"):
            continue
        q = world.inventory.qty(p, material)
        if q > best:
            best = q
            who = p
    return best, who


def tick_genesis_world_feed(world: World) -> None:
    """Every ~16 ticks emit 1–3 digest lines derived from workshops, books, and hub stocks."""
    if world.scenario_id != "genesis":
        return
    if world.tick < 12 or world.tick % 16 != 0:
        return
    headlines: list[str] = []
    sm = _settler_strip_mines(world)
    pm = _player_strip_mines(world)
    total_mines = sum(1 for b in world.plot_buildings if b.get("building_id") == "strip_mine")
    if sm > 0 or pm > 0:
        headlines.append(
            f"Industry scan: {total_mines} strip-mines operating "
            f"({sm} settler-run{'' if sm == 1 else 's'}, {pm} yours)."
        )
    for mid, label in (
        (MaterialId("coal"), "Coal"),
        (MaterialId("grain"), "Grain"),
        (MaterialId("electricity"), "Electricity"),
    ):
        px = best_resting_ask_cents(world, mid)
        if px is not None:
            headlines.append(f"{label} best ask sits at {px}¢ on the exchange.")
    pq = world.inventory.qty(_PLAYER, MaterialId("coal"))
    best_s, leader = _max_settler_inventory(world, MaterialId("coal"))
    if pq > 0 and pq >= best_s and pq >= 6:
        headlines.append("You are the largest coal holder among surveyed settlers this cycle.")
    elif leader is not None and best_s >= 8 and pq < best_s:
        headlines.append(
            f"Coal leadership: {leader} is listing deeper inventory than you this week — watch their clips."
        )
    for hub, hlabel, mid, need in (
        (_HUB_E, "Eastern pop hub", MaterialId("grain"), 20),
        (_HUB_W, "Western pop hub", MaterialId("grain"), 20),
        (_HUB_E, "Eastern pop hub", MaterialId("electricity"), 24),
    ):
        if hub not in world.parties:
            continue
        q = world.inventory.qty(hub, mid)
        if q < need:
            headlines.append(f"{hlabel} is tight on {mid} ({q} u in stock vs ~{need} u comfort).")
    if not headlines:
        return
    rng = world.rng(f"gen:digest_pick:{world.tick}")
    k = min(3, len(headlines))
    picks = rng.sample(range(len(headlines)), k=k) if len(headlines) > 3 else list(range(len(headlines)))
    parts = [headlines[i] for i in sorted(picks)]
    log_event(world, "world_feed", " ".join(parts))


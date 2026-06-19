"""Rolling trade-volume index — consolidator/analytics reads without scanning event_log."""

from __future__ import annotations

from typing import Any, Final

from realm.world import World

_TRADE_KINDS: Final[frozenset[str]] = frozenset({"market_match", "market_buy", "market_sell"})
# Keep one week past the longest consolidator window (7 game-days).
_MAX_RETAIN_TICKS: Final[int] = 8 * 7 * 1440
_MAX_ENTRIES: Final[int] = 12_000

__all__ = [
    "note_trade_event",
    "trade_volume_by_material_window",
    "trade_volume_by_party_for_material",
    "match_seller_volumes_by_material_window",
    "party_trade_share_bps",
]


def _store(world: World) -> dict[str, Any]:
    return world.scenario_state.setdefault("trade_volume_index", {"entries": []})


def _ev_trade_qty(ev: dict[str, Any]) -> int:
    kind = str(ev.get("kind") or "")
    if kind == "market_buy":
        return int(ev.get("filled") or ev.get("qty") or 0)
    if kind in ("market_match", "market_sell"):
        return int(ev.get("qty") or 0)
    return 0


def _ev_seller(ev: dict[str, Any]) -> str:
    seller = ev.get("seller")
    if seller:
        return str(seller)
    if ev.get("kind") == "market_sell":
        return str(ev.get("party") or "")
    return ""


def _prune(world: World, entries: list[dict[str, Any]]) -> None:
    cutoff = int(world.tick) - _MAX_RETAIN_TICKS
    while entries and int(entries[0]["tick"]) < cutoff:
        entries.pop(0)
    overflow = len(entries) - _MAX_ENTRIES
    if overflow > 0:
        del entries[:overflow]


def note_trade_event(world: World, row: dict[str, Any]) -> None:
    """Record one trade row (called from ``log_event`` for trade kinds)."""
    kind = str(row.get("kind") or "")
    if kind not in _TRADE_KINDS:
        return
    material = row.get("material")
    if not material:
        return
    qty = _ev_trade_qty(row)
    if qty <= 0:
        return
    entries: list[dict[str, Any]] = _store(world)["entries"]
    entries.append(
        {
            "tick": int(row.get("tick", world.tick)),
            "kind": kind,
            "material": str(material),
            "qty": qty,
            "seller": _ev_seller(row),
        }
    )
    _prune(world, entries)


def _entries(world: World) -> list[dict[str, Any]]:
    store = _store(world)
    entries: list[dict[str, Any]] = store["entries"]
    if entries or store.get("backfilled"):
        return entries
    # One-time backfill for saves/tests bootstrapped before the index existed.
    for ev in world.event_log:
        note_trade_event(world, ev)
    store["backfilled"] = True
    return entries


def trade_volume_by_material_window(world: World, *, window_ticks: int) -> dict[str, int]:
    cutoff = int(world.tick) - int(window_ticks)
    totals: dict[str, int] = {}
    for row in reversed(_entries(world)):
        if int(row["tick"]) < cutoff:
            break
        mid = str(row["material"])
        totals[mid] = totals.get(mid, 0) + int(row["qty"])
    return totals


def trade_volume_by_party_for_material(
    world: World, material: str, *, window_ticks: int
) -> dict[str, int]:
    cutoff = int(world.tick) - int(window_ticks)
    mat_s = str(material)
    totals: dict[str, int] = {}
    for row in reversed(_entries(world)):
        if int(row["tick"]) < cutoff:
            break
        if str(row["material"]) != mat_s:
            continue
        seller = str(row.get("seller") or "")
        if not seller:
            continue
        totals[seller] = totals.get(seller, 0) + int(row["qty"])
    return totals


def match_seller_volumes_by_material_window(
    world: World, *, window_ticks: int
) -> dict[str, dict[str, int]]:
    """``{material: {seller_party: qty}}`` from ``market_match`` fills only."""
    cutoff = int(world.tick) - int(window_ticks)
    out: dict[str, dict[str, int]] = {}
    for row in reversed(_entries(world)):
        if int(row["tick"]) < cutoff:
            break
        if str(row.get("kind") or "") != "market_match":
            continue
        material = str(row["material"])
        seller = str(row.get("seller") or "")
        if not material or not seller:
            continue
        qty = int(row["qty"])
        if qty <= 0:
            continue
        bucket = out.setdefault(material, {})
        bucket[seller] = bucket.get(seller, 0) + qty
    return out


def party_trade_share_bps(
    world: World, party: str, material: str, *, window_ticks: int
) -> int:
    per_party = trade_volume_by_party_for_material(
        world, material, window_ticks=window_ticks
    )
    total = sum(per_party.values())
    if total <= 0:
        return 0
    mine = per_party.get(str(party), 0)
    return (mine * 10_000) // total

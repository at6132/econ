"""Road segments (Sprint 6 — Phase A).

A ``RoadSegment`` connects two adjacent plots, reduces the per-tile shipping
cost on that edge by 50%, and lets its owner collect an optional ad-valorem
toll (0–10%) on goods value transiting the segment.

Roads are not tied to a plot in ``world.plot_buildings``; they sit on an edge.
The build action consumes ``BUILD_MATERIALS`` from the builder's inventory and
pays ``BUILD_COST_CENTS`` to the system reserve.
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.geo import manhattan
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import RoadSegment, World

BUILD_COST_CENTS: int = 12_000
BUILD_MATERIALS: dict[MaterialId, int] = {
    MaterialId("lumber"): 2,
    MaterialId("stone"): 2,
}
MAX_TOLL_PCT: int = 10


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────


def _canonical_edge(a: PlotId, b: PlotId) -> tuple[str, str]:
    """Edge key — order-agnostic so we can look up roads regardless of direction."""
    sa, sb = str(a), str(b)
    return (sa, sb) if sa <= sb else (sb, sa)


def find_segment_between(
    world: World, a: PlotId, b: PlotId
) -> RoadSegment | None:
    """Return the road segment on the edge ``(a, b)`` if one exists."""
    target = _canonical_edge(a, b)
    for seg in world.road_segments:
        if _canonical_edge(seg.from_plot, seg.to_plot) == target:
            return seg
    return None


def _are_adjacent(world: World, a: PlotId, b: PlotId) -> bool:
    """Manhattan-distance-1 check, both plots must exist."""
    pa = world.plots.get(a)
    pb = world.plots.get(b)
    if pa is None or pb is None:
        return False
    return manhattan(world, a, b) == 1


# ────────────────────────────────────────────────────────────────────────
# Build / configure actions
# ────────────────────────────────────────────────────────────────────────


def build_road(
    world: World,
    party: PartyId,
    from_plot_id: PlotId,
    to_plot_id: PlotId,
) -> dict[str, Any]:
    """Build a road segment on the edge between two adjacent plots.

    Costs ``BUILD_COST_CENTS`` (to system reserve) plus ``BUILD_MATERIALS``
    consumed from the builder's inventory. Returns ``{ok, segment_id}`` or
    ``{ok: False, reason}``.
    """
    if str(from_plot_id) == str(to_plot_id):
        return {"ok": False, "reason": "from and to plots must differ"}
    if not _are_adjacent(world, from_plot_id, to_plot_id):
        return {"ok": False, "reason": "plots are not adjacent"}
    if find_segment_between(world, from_plot_id, to_plot_id) is not None:
        return {"ok": False, "reason": "road already exists on this edge"}
    # Materials check first (cheap, before touching money).
    for mat, need in BUILD_MATERIALS.items():
        if world.inventory.qty(party, mat) < need:
            return {"ok": False, "reason": f"insufficient {mat} (need {need})"}
    cash = party_cash_account(party)
    world.ledger.ensure_account(cash)
    if world.ledger.balance(cash) < BUILD_COST_CENTS:
        return {"ok": False, "reason": "insufficient cash for road"}
    tr = world.ledger.transfer(
        debit=cash, credit=system_reserve_account(), amount_cents=BUILD_COST_CENTS
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    # Consume materials after money is locked in.
    consumed: list[tuple[MaterialId, int]] = []
    for mat, need in BUILD_MATERIALS.items():
        rm = world.inventory.remove(party, mat, need)
        if isinstance(rm, MatterErr):
            # Roll back materials we already removed, then refund money.
            for cm, cq in consumed:
                world.inventory.add(party, cm, cq)
            world.ledger.transfer(
                debit=system_reserve_account(), credit=cash, amount_cents=BUILD_COST_CENTS
            )
            return {"ok": False, "reason": rm.reason}
        consumed.append((mat, need))
    world.next_road_segment_seq += 1
    sid = f"road-{world.next_road_segment_seq}"
    seg = RoadSegment(
        segment_id=sid,
        from_plot=PlotId(str(from_plot_id)),
        to_plot=PlotId(str(to_plot_id)),
        owner=PartyId(str(party)),
        built_at_tick=int(world.tick),
        toll_rate_pct=0,
    )
    world.road_segments.append(seg)
    log_event(
        world,
        "road_built",
        f"{party} built road {sid} ({from_plot_id} ↔ {to_plot_id})",
        party=str(party),
        segment_id=sid,
        from_plot=str(from_plot_id),
        to_plot=str(to_plot_id),
    )
    return {"ok": True, "segment_id": sid}


def set_road_toll(
    world: World, party: PartyId, segment_id: str, toll_rate_pct: int
) -> dict[str, Any]:
    """Owner sets the toll rate on a segment (0–10%)."""
    if not (0 <= int(toll_rate_pct) <= MAX_TOLL_PCT):
        return {"ok": False, "reason": f"toll must be 0..{MAX_TOLL_PCT}%"}
    for seg in world.road_segments:
        if seg.segment_id != segment_id:
            continue
        if str(seg.owner) != str(party):
            return {"ok": False, "reason": "not the road owner"}
        old = int(seg.toll_rate_pct)
        seg.toll_rate_pct = int(toll_rate_pct)
        log_event(
            world,
            "road_toll_set",
            f"{party} set toll on {segment_id} to {toll_rate_pct}% (was {old}%)",
            party=str(party),
            segment_id=segment_id,
            toll_rate_pct=int(toll_rate_pct),
        )
        return {"ok": True, "segment_id": segment_id, "toll_rate_pct": int(toll_rate_pct)}
    return {"ok": False, "reason": "unknown road segment"}


# ────────────────────────────────────────────────────────────────────────
# Path-based road lookup (for movement cost reduction + toll collection)
# ────────────────────────────────────────────────────────────────────────


def deterministic_path_edges(
    world: World, from_plot_id: PlotId, to_plot_id: PlotId
) -> list[tuple[PlotId, PlotId]]:
    """A deterministic Manhattan path from ``from_plot_id`` to ``to_plot_id``.

    Walks x first, then y. Returns the ordered list of adjacent-plot edges
    along the path, or an empty list if either plot is unknown.

    Determinism matters: roads either lie on the chosen path or they don't,
    and the same call always returns the same path so shipping cost and
    toll collection match.
    """
    pa = world.plots.get(from_plot_id)
    pb = world.plots.get(to_plot_id)
    if pa is None or pb is None:
        return []
    # Reverse-lookup plot id by (x, y).
    by_xy: dict[tuple[int, int], PlotId] = {(p.x, p.y): pid for pid, p in world.plots.items()}
    edges: list[tuple[PlotId, PlotId]] = []
    cx, cy = pa.x, pa.y
    cur = from_plot_id
    dx = 1 if pb.x > pa.x else -1
    while cx != pb.x:
        nxt_xy = (cx + dx, cy)
        nxt = by_xy.get(nxt_xy)
        if nxt is None:
            return []
        edges.append((cur, nxt))
        cur = nxt
        cx += dx
    dy = 1 if pb.y > pa.y else -1
    while cy != pb.y:
        nxt_xy = (cx, cy + dy)
        nxt = by_xy.get(nxt_xy)
        if nxt is None:
            return []
        edges.append((cur, nxt))
        cur = nxt
        cy += dy
    return edges


def road_path_summary(
    world: World, from_plot_id: PlotId, to_plot_id: PlotId
) -> dict[str, Any]:
    """Summarise the road coverage along the deterministic A→B path.

    Returns:
      - ``total_tiles``: Manhattan distance (= number of edges).
      - ``road_tiles``: edges that have a road built on them.
      - ``segments``: ordered list of ``RoadSegment`` objects on the path.
    """
    edges = deterministic_path_edges(world, from_plot_id, to_plot_id)
    segs: list[RoadSegment] = []
    for a, b in edges:
        seg = find_segment_between(world, a, b)
        if seg is not None:
            segs.append(seg)
    return {
        "total_tiles": len(edges),
        "road_tiles": len(segs),
        "segments": segs,
    }


def compute_road_savings_and_tolls(
    world: World,
    *,
    from_plot_id: PlotId,
    to_plot_id: PlotId,
    per_tile_cents: int,
    goods_value_cents: int,
    shipper: PartyId,
) -> dict[str, Any]:
    """Compute per-tile savings and per-segment toll allocations for a shipment.

    Returns:
      - ``savings_cents``: per-tile cents that should be subtracted from the
        shipping fee because roads cover those tiles (each road covers one tile
        at 50% discount).
      - ``tolls``: ``[(owner_party_id, segment_id, toll_cents)]`` — non-self
        owners only. Self-owned roads still grant the savings but no toll is
        moved.
      - ``segments``: the segments along the path (informational).
    """
    summary = road_path_summary(world, from_plot_id, to_plot_id)
    segments: list[RoadSegment] = summary["segments"]
    # Savings: 50% off per-tile cost for each tile covered by a road.
    savings_cents = (per_tile_cents * len(segments)) // 2
    tolls: list[tuple[PartyId, str, int]] = []
    shipper_s = str(shipper)
    for seg in segments:
        if int(seg.toll_rate_pct) <= 0:
            continue
        if str(seg.owner) == shipper_s:
            continue
        amount = (int(goods_value_cents) * int(seg.toll_rate_pct)) // 100
        if amount <= 0:
            continue
        tolls.append((PartyId(str(seg.owner)), seg.segment_id, int(amount)))
    return {
        "savings_cents": int(savings_cents),
        "tolls": tolls,
        "segments": segments,
    }


# ────────────────────────────────────────────────────────────────────────
# Public-view helpers (for /world and /roads endpoints)
# ────────────────────────────────────────────────────────────────────────


def road_segment_public_dict(seg: RoadSegment) -> dict[str, Any]:
    return {
        "segment_id": seg.segment_id,
        "from_plot": str(seg.from_plot),
        "to_plot": str(seg.to_plot),
        "owner": str(seg.owner),
        "built_at_tick": int(seg.built_at_tick),
        "toll_rate_pct": int(seg.toll_rate_pct),
    }


def all_roads_public(world: World) -> list[dict[str, Any]]:
    return [road_segment_public_dict(s) for s in world.road_segments]

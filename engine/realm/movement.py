"""Goods in transit — Law 3 (time + distance).

Shipping fee (integer cents): ``BASE_SHIP_FEE_CENTS + manhattan(from, to) * PER_TILE_SHIP_CENTS``.
Paid to ``system:reserve`` on dispatch. Arrival tick uses distance × ``TRANSIT_BUFFER_TICKS`` plus buffer.
"""

from __future__ import annotations

from realm.event_log import log_event
from realm.geo import manhattan
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.storage_caps import try_add_inventory
from realm.world import InTransit, World

BASE_SHIP_FEE_CENTS = 100
PER_TILE_SHIP_CENTS = 50
TRANSIT_BUFFER_TICKS = 1  # minimum extra ticks after distance


def _plot_owned(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


def dispatch_shipment(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    from_plot_id: PlotId,
    to_plot_id: PlotId,
) -> dict:
    """
    Ship goods between plots the party owns; fee to system; arrives after distance-based ticks.

    Returns {ok: True, shipment_id, arrive_tick, fee_cents} | {ok: False, reason}.
    """
    if qty <= 0:
        return {"ok": False, "reason": "quantity must be positive"}
    if not _plot_owned(world, party, from_plot_id) or not _plot_owned(world, party, to_plot_id):
        return {"ok": False, "reason": "must own both plots"}
    if from_plot_id == to_plot_id:
        return {"ok": False, "reason": "same plot"}
    if world.inventory.qty(party, material) < qty:
        return {"ok": False, "reason": "insufficient material"}
    dist = manhattan(world, from_plot_id, to_plot_id)
    fee = BASE_SHIP_FEE_CENTS + dist * PER_TILE_SHIP_CENTS
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < fee:
        return {"ok": False, "reason": "insufficient cash for shipping"}
    pay = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=fee,
    )
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}
    rm = world.inventory.remove(party, material, qty)
    if isinstance(rm, MatterErr):
        world.ledger.transfer(debit=system_reserve_account(), credit=cash, amount_cents=fee)
        return {"ok": False, "reason": rm.reason}
    arrive = world.tick + dist * TRANSIT_BUFFER_TICKS + TRANSIT_BUFFER_TICKS
    world.next_shipment_seq += 1
    sid = f"ship-{world.next_shipment_seq}"
    world.in_transit.append(
        InTransit(
            shipment_id=sid,
            party=party,
            material=material,
            qty=qty,
            dest_plot_id=to_plot_id,
            arrive_tick=arrive,
            from_plot_id=from_plot_id,
        )
    )
    log_event(
        world,
        "ship_dispatch",
        f"{party} shipped {qty}×{material} → {to_plot_id} (arrive tick {arrive}, fee ${fee / 100:.2f})",
        party=str(party),
        material=str(material),
        qty=qty,
        dest_plot_id=str(to_plot_id),
        arrive_tick=arrive,
        fee_cents=fee,
    )
    return {"ok": True, "shipment_id": sid, "arrive_tick": arrive, "fee_cents": fee}


def deliver_transit(world: World) -> None:
    """Deliver shipments whose arrive_tick is <= current tick (before tick increments)."""
    t = world.tick
    keep: list[InTransit] = []
    for s in world.in_transit:
        if s.arrive_tick > t:
            keep.append(s)
            continue
        ad = try_add_inventory(world, s.party, s.material, s.qty)
        if isinstance(ad, MatterErr):
            keep.append(s)
            continue
        log_event(
            world,
            "ship_deliver",
            f"Delivered {s.qty}×{s.material} to {s.party} at {s.dest_plot_id}",
            party=str(s.party),
            material=str(s.material),
            qty=s.qty,
            dest_plot_id=str(s.dest_plot_id),
            shipment_id=s.shipment_id,
        )
    world.in_transit = keep

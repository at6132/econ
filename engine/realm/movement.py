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
from realm.plot_logistics import plot_output_qty, remove_plot_output, try_add_plot_output, uses_plot_logistics
from realm.storage_caps import try_add_inventory
from realm.world import InTransit, World

BASE_SHIP_FEE_CENTS = 100
PER_TILE_SHIP_CENTS = 50
TRANSIT_BUFFER_TICKS = 1  # minimum extra ticks after distance

# Unloading / receiving (dock handling): paid when goods are accepted at destination; all parties alike.
RECEIVING_FEE_BASE_CENTS = 25
RECEIVING_FEE_EXTRA_PER_CHUNK_CENTS = 1
RECEIVING_FEE_CHUNK_UNITS = 20  # +1¢ per this many units after the first


def receiving_fee_cents(qty: int) -> int:
    """Deterministic handling fee for a delivered shipment size."""
    if qty <= 0:
        return 0
    return RECEIVING_FEE_BASE_CENTS + max(0, qty - 1) // RECEIVING_FEE_CHUNK_UNITS * RECEIVING_FEE_EXTRA_PER_CHUNK_CENTS


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
    inv_q = world.inventory.qty(party, material)
    stash_q = plot_output_qty(world, from_plot_id, material) if uses_plot_logistics(world, party) else 0
    if inv_q + stash_q < qty:
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
    need = qty
    take_inv = min(need, inv_q)
    if take_inv > 0:
        rm = world.inventory.remove(party, material, take_inv)
        if isinstance(rm, MatterErr):
            world.ledger.transfer(debit=system_reserve_account(), credit=cash, amount_cents=fee)
            return {"ok": False, "reason": rm.reason}
    need -= take_inv
    if need > 0:
        r2 = remove_plot_output(world, party, from_plot_id, material, need)
        if isinstance(r2, MatterErr):
            if take_inv > 0:
                world.inventory.add(party, material, take_inv)
            world.ledger.transfer(debit=system_reserve_account(), credit=cash, amount_cents=fee)
            return {"ok": False, "reason": r2.reason}
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
        recv_fee = receiving_fee_cents(s.qty)
        cash = party_cash_account(s.party)
        if recv_fee > 0 and world.ledger.balance(cash) < recv_fee:
            keep.append(s)
            log_event(
                world,
                "ship_deliver_blocked",
                f"{s.party} could not pay receiving fee {recv_fee}¢ for {s.shipment_id} — shipment held",
                party=str(s.party),
                shipment_id=s.shipment_id,
                receiving_fee_cents=recv_fee,
            )
            continue
        if uses_plot_logistics(world, s.party):
            ad = try_add_plot_output(world, s.dest_plot_id, s.party, s.material, s.qty)
        else:
            ad = try_add_inventory(world, s.party, s.material, s.qty)
        if isinstance(ad, MatterErr):
            keep.append(s)
            continue
        if recv_fee > 0:
            pay_recv = world.ledger.transfer(
                debit=cash,
                credit=system_reserve_account(),
                amount_cents=recv_fee,
            )
            if isinstance(pay_recv, MoneyErr):
                if uses_plot_logistics(world, s.party):
                    rb = remove_plot_output(world, s.party, s.dest_plot_id, s.material, s.qty)
                    assert not isinstance(rb, MatterErr)
                else:
                    rb2 = world.inventory.remove(s.party, s.material, s.qty)
                    assert not isinstance(rb2, MatterErr)
                keep.append(s)
                continue
        log_event(
            world,
            "ship_deliver",
            f"Delivered {s.qty}×{s.material} to {s.party} at {s.dest_plot_id} (receiving {recv_fee}¢)",
            party=str(s.party),
            material=str(s.material),
            qty=s.qty,
            dest_plot_id=str(s.dest_plot_id),
            shipment_id=s.shipment_id,
            receiving_fee_cents=recv_fee,
        )
    world.in_transit = keep

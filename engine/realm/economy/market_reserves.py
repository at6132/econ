"""Plot stock reserved for resting market asks — goods stay on-site until fill or cancel."""

from __future__ import annotations

from dataclasses import dataclass

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr, MatterOk, MatterResult
from realm.infrastructure.plot_logistics import plot_output_qty
from realm.production.storage_caps import is_carried_material, party_uses_plot_storage
from realm.world import World


@dataclass
class PlotMarketReserve:
    order_id: str
    party: PartyId
    plot_id: PlotId
    material: MaterialId
    qty: int


def _reserve_list(world: World) -> list[PlotMarketReserve]:
    raw = getattr(world, "plot_market_reserves", None)
    if raw is None:
        world.plot_market_reserves = []
        return world.plot_market_reserves
    return raw


def plot_reserved_qty(world: World, plot_id: PlotId, material: MaterialId) -> int:
    pid = str(plot_id)
    ms = str(material)
    return sum(
        int(r.qty)
        for r in _reserve_list(world)
        if str(r.plot_id) == pid and str(r.material) == ms
    )


def plot_fob_committed_qty(world: World, plot_id: PlotId, material: MaterialId) -> int:
    """Units sold FOB awaiting buyer pickup (still on the listing plot)."""
    pid = str(plot_id)
    ms = str(material)
    total = 0
    for row in getattr(world, "market_fob_pickups", []):
        if str(getattr(row, "from_plot_id", "")) != pid:
            continue
        if str(getattr(row, "material", "")) != ms:
            continue
        total += int(getattr(row, "qty", 0))
    return total


def plot_available_qty(world: World, plot_id: PlotId, material: MaterialId) -> int:
    on_hand = plot_output_qty(world, plot_id, material)
    held = plot_reserved_qty(world, plot_id, material) + plot_fob_committed_qty(
        world, plot_id, material
    )
    return max(0, on_hand - held)


def reserve_plot_for_ask(
    world: World,
    *,
    order_id: str,
    party: PartyId,
    plot_id: PlotId,
    material: MaterialId,
    qty: int,
) -> MatterResult:
    if qty <= 0:
        return MatterErr(reason="invalid reserve qty")
    avail = plot_available_qty(world, plot_id, material)
    if avail < qty:
        return MatterErr(
            reason=f"only {avail} {material} free on {plot_id} ({plot_reserved_qty(world, plot_id, material)} listed)"
        )
    _reserve_list(world).append(
        PlotMarketReserve(
            order_id=order_id,
            party=party,
            plot_id=plot_id,
            material=material,
            qty=int(qty),
        )
    )
    return MatterOk()


def release_reserve_for_order(world: World, order_id: str) -> int:
    lst = _reserve_list(world)
    freed = sum(int(r.qty) for r in lst if r.order_id == order_id)
    world.plot_market_reserves = [r for r in lst if r.order_id != order_id]
    return freed


def consume_reserve_for_order(world: World, order_id: str, qty: int) -> MatterResult:
    if qty <= 0:
        return MatterOk()
    lst = _reserve_list(world)
    remaining = int(qty)
    new_lst: list[PlotMarketReserve] = []
    for r in lst:
        if r.order_id != order_id:
            new_lst.append(r)
            continue
        if remaining <= 0:
            new_lst.append(r)
            continue
        take = min(remaining, int(r.qty))
        remaining -= take
        left = int(r.qty) - take
        if left > 0:
            new_lst.append(
                PlotMarketReserve(
                    order_id=r.order_id,
                    party=r.party,
                    plot_id=r.plot_id,
                    material=r.material,
                    qty=left,
                )
            )
    if remaining > 0:
        return MatterErr(reason="reserve shortfall")
    world.plot_market_reserves = new_lst
    return MatterOk()


def reserves_for_party(world: World, party: PartyId) -> list[dict]:
    out: list[dict] = []
    for r in _reserve_list(world):
        if r.party != party:
            continue
        out.append(
            {
                "order_id": r.order_id,
                "plot_id": str(r.plot_id),
                "material": str(r.material),
                "qty": int(r.qty),
            }
        )
    return out


def pick_plot_with_available_stock(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    *,
    preferred: PlotId | None = None,
) -> PlotId | None:
    if preferred is not None and plot_available_qty(world, preferred, material) >= qty:
        return preferred
    for pid in sorted(
        (p.plot_id for p in world.plots.values() if p.owner == party),
        key=str,
    ):
        if plot_available_qty(world, pid, material) >= qty:
            return pid
    return None


def uses_plot_market_reserve(world: World, party: PartyId, material: MaterialId) -> bool:
    return party_uses_plot_storage(world, party) and not is_carried_material(material)

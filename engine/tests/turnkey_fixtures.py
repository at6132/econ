"""Grant self_materials + enough cash for turnkey builds (tests only)."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.infrastructure.power_grid import plot_has_grid_capacity
from realm.world import World
from stage_materials import stage_material


# How much to give each test party for turnkey builds.
# High so any seeded blueprint can be built without cash checks failing.
_TEST_CASH_CENTS: int = 2_000_000_00  # $2,000,000


def ensure_plot_grid_power(world: World, plot_id: PlotId) -> None:
    """Place an active ``power_shed`` on ``plot_id`` so grid-backed recipes can run."""
    if plot_has_grid_capacity(world, plot_id):
        return
    plot = world.plots.get(plot_id)
    owner = str(plot.owner) if plot is not None and plot.owner else "player"
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) == str(plot_id) and pb.blueprint_id == "power_shed":
            return
    from realm.world.plot_scale import cells_free
    from realm.world.placed_buildings import PlacedBuilding, register_placed_building

    gx, gy = 1, 0
    if not cells_free(str(plot_id), world, gx, gy, 1, 1):
        gx, gy = 0, 1
    world.next_building_instance_seq += 1
    iid = f"b{world.next_building_instance_seq:06d}"
    pb = PlacedBuilding(
        instance_id=iid,
        blueprint_id="power_shed",
        plot_id=str(plot_id),
        grid_x=gx,
        grid_y=gy,
        built_at_tick=int(world.tick),
        built_by=owner,
        status="active",
        efficiency_pct=100,
        missed_maintenance_cycles=0,
        due_at_tick=int(world.tick) + 7_200,
    )
    register_placed_building(world, pb)
    world.building_maintenance[iid] = {
        "due_at_tick": int(world.tick) + 7_200,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }


def grant_turnkey_self_materials(
    world: World,
    party: PartyId,
    building_id: str,
    *,
    count: int = 1,
    plot_id: PlotId | None = None,
) -> None:
    """
    Stock ``count`` copies of the construction_materials for a blueprint build,
    AND grant enough cash to cover any turnkey pricing.

    Works for both the legacy BUILDINGS dict and the new Blueprint system.
    """
    # Grant cash first — covers turnkey market-based pricing
    src = system_reserve_account()
    dst = party_cash_account(party)
    current = world.ledger.balance(dst)
    if current < _TEST_CASH_CENTS:
        world.ledger.transfer(
            debit=src,
            credit=dst,
            amount_cents=_TEST_CASH_CENTS - current,
        )

    # Grant materials — try Blueprint system first, fall back to old BUILDINGS
    _grant_blueprint_materials(world, party, building_id, count, plot_id=plot_id)
    _ensure_turnkey_market_liquidity(world, building_id, count)


def _grant_blueprint_materials(
    world: World,
    party: PartyId,
    building_id: str,
    count: int,
    *,
    plot_id: PlotId | None = None,
) -> None:
    """Grant construction_materials from the Blueprint registry if present."""
    bp = world.blueprints.get(building_id)
    if bp is not None:
        for mid_s, qty in bp.construction_materials.items():
            ad = stage_material(
                world, party, MaterialId(str(mid_s)), int(qty) * count, plot_id=plot_id
            )
            assert not isinstance(ad, MatterErr), ad
        return

    # Fall back to legacy BUILDINGS dict (for any test using non-blueprint buildings)
    try:
        from realm.production.buildings import BUILDINGS  # type: ignore[attr-defined]

        spec = BUILDINGS.get(building_id)
        if spec:
            for mid_s, qty in (spec.get("self_materials") or {}).items():
                ad = stage_material(
                    world, party, MaterialId(str(mid_s)), int(qty) * count, plot_id=plot_id
                )
                assert not isinstance(ad, MatterErr), ad
    except (ImportError, AttributeError):
        pass  # BUILDINGS may no longer exist; blueprint system handles it


def _ensure_turnkey_market_liquidity(
    world: World, building_id: str, count: int
) -> None:
    """List construction inputs on genesis_exchange so turnkey market_buy can fill."""
    from realm.economy.markets import place_sell_order

    bp = world.blueprints.get(building_id)
    if bp is None:
        return
    seller = PartyId("genesis_exchange")
    for mid_s, qty in bp.construction_materials.items():
        mat = MaterialId(str(mid_s))
        need = int(qty) * count + 20
        ad = world.inventory.add(seller, mat, need)
        assert not isinstance(ad, MatterErr), ad
        assert place_sell_order(world, seller, mat, need, 100)["ok"]

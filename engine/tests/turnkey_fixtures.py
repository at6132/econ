"""Grant self_materials + enough cash for turnkey builds (tests only)."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world import World
from stage_materials import stage_material


# How much to give each test party for turnkey builds.
# High so any seeded blueprint can be built without cash checks failing.
_TEST_CASH_CENTS: int = 2_000_000_00  # $2,000,000


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

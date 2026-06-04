"""Blueprint registration and placement on plot grids."""

from __future__ import annotations

from realm.actions._shared import ActionResult
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import AccountId, MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import BUILD_CONTRACTED_TICKS, BUILD_SIMPLE_TICKS
from realm.economy.markets import market_buy
from realm.economy.pricing import fair_value_cents
from realm.events.event_log import log_event
from realm.production.blueprints import Blueprint, blueprint_public_dict
from realm.production.buildings import BUILDINGS
from realm.production.recipes import RECIPES
from realm.world import World
from realm.world.placed_buildings import (
    PlacedBuilding,
    register_placed_building,
    sync_plot_buildings_from_placed,
)
from realm.world.plot_scale import (
    cells_free,
    cells_occupied,
    plot_deed_grid_cells,
    plot_grid_side_for_id,
)


def _turnkey_unit_price_cents(world: World, mat_id: str) -> int:
    """Best ask on the book, else fair-value anchor (never a punitive placeholder)."""
    mid = MaterialId(mat_id)
    asks = world.market_asks_by_material.get(str(mat_id), [])
    if not asks:
        asks = world.market_asks_by_material.get(mid, [])
    if asks:
        return min(int(a.price_per_unit_cents) for a in asks)
    return int(fair_value_cents(mid) or 100)


def compute_turnkey_cost_cents(world: World, bp: Blueprint) -> int:
    """Cash needed for turnkey: labor plus materials (market or fair-value estimate)."""
    total = int(bp.construction_labor_cents)
    for mat_id, qty in bp.construction_materials.items():
        q = int(qty)
        if q > 0:
            total += _turnkey_unit_price_cents(world, str(mat_id)) * q
    return total


def turnkey_cost_public(world: World, bp: Blueprint) -> dict[str, int | str | dict[str, int]]:
    """UI-facing turnkey breakdown (matches ``place_blueprint`` turnkey charging)."""
    labor = int(bp.construction_labor_cents)
    mat_total = 0
    lines: dict[str, int] = {}
    uses_market = True
    for mat_id, qty in bp.construction_materials.items():
        q = int(qty)
        if q <= 0:
            continue
        mid = MaterialId(mat_id)
        asks = world.market_asks_by_material.get(str(mat_id), [])
        if not asks:
            asks = world.market_asks_by_material.get(mid, [])
        if asks:
            unit = min(int(a.price_per_unit_cents) for a in asks)
        else:
            uses_market = False
            unit = int(fair_value_cents(mid) or 100)
        line = unit * q
        lines[str(mat_id)] = line
        mat_total += line
    return {
        "turnkey_estimate_cents": labor + mat_total,
        "turnkey_labor_cents": labor,
        "turnkey_materials_cents": mat_total,
        "turnkey_material_lines_cents": lines,
        "turnkey_pricing": "market" if uses_market else "fair_value",
    }


def _settle_turnkey_materials(
    world: World, party: PartyId, bp: Blueprint, cash: AccountId
) -> ActionResult | None:
    """Buy construction inputs from the book or pay fair-value into the system reserve."""
    for mat_id, qty in bp.construction_materials.items():
        q = int(qty)
        if q <= 0:
            continue
        mid = MaterialId(mat_id)
        asks = world.market_asks_by_material.get(str(mat_id), [])
        if not asks:
            asks = world.market_asks_by_material.get(mid, [])
        if asks:
            br = market_buy(
                world,
                party,
                mid,
                q,
                max_price_per_unit_cents=999_999,
            )
            if not br.get("ok"):
                return {
                    "ok": False,
                    "reason": str(br.get("reason", "market buy failed")),
                }
        else:
            unit = int(fair_value_cents(mid) or 100)
            cost = unit * q
            tr = world.ledger.transfer(
                debit=cash,
                credit=system_reserve_account(),
                amount_cents=cost,
            )
            if isinstance(tr, MoneyErr):
                return {"ok": False, "reason": tr.reason}
    return None


def _next_blueprint_id(world: World) -> str:
    seq = int(world.scenario_state.get("next_blueprint_seq", 0)) + 1
    world.scenario_state["next_blueprint_seq"] = seq
    return f"bp_{seq:05d}"


def _next_instance_id(world: World) -> str:
    world.next_building_instance_seq += 1
    return f"pb_{world.next_building_instance_seq:06d}"


def _find_free_position(
    world: World,
    plot_id: str,
    bp: Blueprint,
) -> tuple[int, int] | None:
    gw, gh = plot_grid_side_for_id(world, plot_id)
    for gy in range(gh):
        for gx in range(gw):
            if cells_free(plot_id, world, gx, gy, bp.footprint_w, bp.footprint_h):
                return gx, gy
    return None


def find_free_blueprint_position(
    world: World, plot_id: PlotId, blueprint_id: str
) -> tuple[int, int] | None:
    """First free grid cell (row-major) for ``blueprint_id`` on ``plot_id``."""
    if blueprint_id not in world.blueprints:
        from realm.production.blueprints import seed_world_blueprints

        seed_world_blueprints(world)
    bp = world.blueprints.get(blueprint_id)
    if bp is None:
        return None
    return _find_free_position(world, str(plot_id), bp)


def create_blueprint(
    world: World,
    creator: PartyId,
    name: str,
    description: str,
    footprint_w: int,
    footprint_h: int,
    construction_materials: dict[str, int],
    construction_labor_cents: int,
    construction_ticks: int,
    enabled_recipe_ids: list[str],
    maintenance_interval_ticks: int,
    maintenance_materials: dict[str, int],
    maintenance_grace_ticks: int,
    is_public: bool,
    license_fee_cents: int,
    category: str,
    terrain_requirements: list[str],
    requires_coastal: bool,
    requires_power: bool,
) -> ActionResult:
    if not (1 <= footprint_w <= 10 and 1 <= footprint_h <= 10):
        return {"ok": False, "reason": "footprint must be 1–10 cells in each dimension"}
    footprint_cells = footprint_w * footprint_h
    if footprint_cells > 100:
        return {"ok": False, "reason": "blueprint footprint exceeds maximum plot area (100 cells)"}
    if not name or len(name) > 60:
        return {"ok": False, "reason": "name must be 1–60 characters"}
    from realm.research.fabrication import (
        validate_blueprint_public_license,
        validate_blueprint_registration,
    )

    reg_err = validate_blueprint_registration(
        world, creator, footprint_w, footprint_h, enabled_recipe_ids
    )
    if reg_err:
        return {"ok": False, "reason": reg_err}
    lic_err = validate_blueprint_public_license(world, creator, is_public)
    if lic_err:
        return {"ok": False, "reason": lic_err}
    from realm.production.custom_content import get_recipe

    for recipe_id in enabled_recipe_ids:
        if get_recipe(world, recipe_id) is None:
            return {"ok": False, "reason": f"unknown recipe_id: {recipe_id}"}

    reg_fee = 20_000 + footprint_cells * 5_000
    cash_acct = party_cash_account(creator)
    if world.ledger.balance(cash_acct) < reg_fee:
        return {"ok": False, "reason": f"need ${reg_fee / 100:.2f} to register blueprint"}

    pay = world.ledger.transfer(
        debit=cash_acct, credit=system_reserve_account(), amount_cents=reg_fee
    )
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}

    bid = _next_blueprint_id(world)
    bp = Blueprint(
        blueprint_id=bid,
        name=name,
        description=description,
        footprint_w=footprint_w,
        footprint_h=footprint_h,
        construction_materials=dict(construction_materials),
        construction_labor_cents=int(construction_labor_cents),
        construction_ticks=int(construction_ticks),
        enabled_recipe_ids=list(enabled_recipe_ids),
        maintenance_interval_ticks=int(maintenance_interval_ticks),
        maintenance_materials=dict(maintenance_materials),
        maintenance_grace_ticks=int(maintenance_grace_ticks),
        is_seeded=False,
        creator_party=str(creator),
        is_public=is_public,
        license_fee_cents=int(license_fee_cents),
        license_contract_id=None,
        category=category,
        terrain_requirements=list(terrain_requirements),
        requires_coastal=requires_coastal,
        requires_power=requires_power,
    )
    world.blueprints[bid] = bp
    from realm.production.custom_content import custom_recipes_store

    for rid in enabled_recipe_ids:
        row = custom_recipes_store(world).get(rid)
        if isinstance(row, dict) and str(row.get("creator_party", "")) == str(creator):
            row["requires_building_id"] = bid
    log_event(
        world,
        "blueprint_created",
        f"{creator} created blueprint '{name}' ({footprint_w}×{footprint_h} cells)",
        party=str(creator),
        blueprint_id=bid,
    )
    return {"ok": True, "blueprint_id": bid, "registration_fee_cents": reg_fee}


def place_blueprint(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    blueprint_id: str,
    grid_x: int,
    grid_y: int,
    build_mode: str = "turnkey",
    *,
    sub_plot_id: str | None = None,
) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "plot not found"}

    bp = world.blueprints.get(blueprint_id)
    if bp is None:
        return {"ok": False, "reason": f"blueprint '{blueprint_id}' not found"}

    plot_key = str(plot_id)
    if sub_plot_id:
        sp = world.sub_plots.get(sub_plot_id)
        if sp is None or sp.parent_plot_id != plot_key:
            return {"ok": False, "reason": "sub-plot not found on this plot"}
        if sp.owner is not None and sp.owner != str(party):
            lease = sp.lease_rights
            if not (
                lease
                and lease.get("lessee") == str(party)
                and int(lease.get("expires_tick", 0)) > world.tick
            ):
                return {"ok": False, "reason": "you don't own or lease this sub-plot"}
        abs_gx = sp.grid_x + grid_x
        abs_gy = sp.grid_y + grid_y
        if (
            grid_x < 0
            or grid_y < 0
            or grid_x + bp.footprint_w > sp.grid_w
            or grid_y + bp.footprint_h > sp.grid_h
        ):
            return {"ok": False, "reason": "building exceeds sub-plot bounds"}
    else:
        abs_gx, abs_gy = grid_x, grid_y
        lease_rights = world.scenario_state.get("plot_lease_rights", {}).get(plot_key)
        has_rights = plot.owner == party or (
            lease_rights
            and lease_rights.get("lessee") == str(party)
            and int(lease_rights.get("expires_tick", 0)) > world.tick
        )
        if not has_rights:
            from realm.infrastructure.plot_access import party_may_operate_plot

            if not party_may_operate_plot(world, party, plot_id):
                return {"ok": False, "reason": "you don't own or lease this plot"}

    can_use = bp.is_seeded or bp.creator_party == str(party) or bp.is_public
    if not can_use:
        return {"ok": False, "reason": "you don't have access to this blueprint"}

    if bp.terrain_requirements and str(plot.terrain.value) not in bp.terrain_requirements:
        return {
            "ok": False,
            "reason": f"requires terrain: {bp.terrain_requirements}",
        }
    if bp.requires_coastal:
        from realm.production.recipe_sites import footprint_borders_water, plot_is_coastal

        if not plot_is_coastal(world, plot):
            return {"ok": False, "reason": "requires coastal terrain"}
        if not footprint_borders_water(
            world, plot, abs_gx, abs_gy, bp.footprint_w, bp.footprint_h
        ):
            return {
                "ok": False,
                "reason": "must be placed on the waterfront (footprint touching water)",
            }
    if bp.requires_power:
        from realm.infrastructure.power_grid import get_plot_power_info

        if not get_plot_power_info(world, PlotId(plot_key)).get("powered", False):
            return {"ok": False, "reason": "plot is not on a road-connected grid with power capacity"}

    if not cells_free(plot_key, world, abs_gx, abs_gy, bp.footprint_w, bp.footprint_h):
        return {
            "ok": False,
            "reason": "grid position overlaps an existing building or is out of bounds",
        }

    mode = build_mode
    if mode == "self_contract":
        mode = "self"

    if mode == "turnkey":
        turnkey_cost = compute_turnkey_cost_cents(world, bp)
        cash = party_cash_account(party)
        balance = world.ledger.balance(cash)
        if balance < turnkey_cost:
            return {
                "ok": False,
                "reason": (
                    f"need ${turnkey_cost / 100:.2f} for turnkey build "
                    f"(have ${balance / 100:.2f})"
                ),
            }
        if bp.construction_labor_cents > 0:
            tr = world.ledger.transfer(
                debit=cash,
                credit=system_reserve_account(),
                amount_cents=bp.construction_labor_cents,
            )
            if isinstance(tr, MoneyErr):
                return {"ok": False, "reason": tr.reason}
        mat_err = _settle_turnkey_materials(world, party, bp, cash)
        if mat_err is not None:
            return mat_err
    elif mode == "self":
        from realm.infrastructure.plot_logistics import (
            party_material_on_plot,
            remove_party_plot_stock,
            uses_plot_logistics,
        )
        from realm.production.storage_caps import is_carried_material

        for mat_id, qty in bp.construction_materials.items():
            mid = MaterialId(mat_id)
            need = int(qty)
            if is_carried_material(mid):
                have = world.inventory.qty(party, mid)
            elif uses_plot_logistics(world, party):
                have = party_material_on_plot(world, party, plot_id, mid)
            else:
                have = world.inventory.qty(party, mid)
            if have < need:
                return {"ok": False, "reason": f"missing {mat_id}: need {qty}, have {have}"}
        for mat_id, qty in bp.construction_materials.items():
            mid = MaterialId(mat_id)
            need = int(qty)
            if is_carried_material(mid):
                rm = world.inventory.remove(party, mid, need)
            elif uses_plot_logistics(world, party):
                rm = remove_party_plot_stock(
                    world, party, mid, need, preferred_plot=plot_id
                )
            else:
                rm = world.inventory.remove(party, mid, need)
            if isinstance(rm, MatterErr):
                return {"ok": False, "reason": rm.reason}
    elif mode not in ("construction_order",):
        return {"ok": False, "reason": "build_mode must be turnkey, self, or construction_order"}

    if bp.license_fee_cents > 0 and bp.creator_party and bp.creator_party != str(party):
        creator = PartyId(bp.creator_party)
        lic = world.ledger.transfer(
            debit=party_cash_account(party),
            credit=party_cash_account(creator),
            amount_cents=bp.license_fee_cents,
        )
        if isinstance(lic, MoneyErr):
            return {"ok": False, "reason": lic.reason}
        log_event(
            world,
            "blueprint_license_fee_paid",
            f"{party} paid {bp.license_fee_cents}¢ license fee to {creator} for '{bp.name}'",
            party=str(party),
            creator=str(creator),
            blueprint_id=blueprint_id,
        )

    completes = world.tick + int(bp.construction_ticks)
    status = "construction" if bp.construction_ticks > 0 else "active"
    due = (
        completes + int(bp.maintenance_interval_ticks)
        if bp.maintenance_interval_ticks > 0
        else 0
    )
    if mode == "turnkey":
        build_cost_cents = compute_turnkey_cost_cents(world, bp)
    else:
        build_cost_cents = int(bp.construction_labor_cents)
        for mat_id, qty in bp.construction_materials.items():
            build_cost_cents += _turnkey_unit_price_cents(world, str(mat_id)) * int(qty)
    iid = _next_instance_id(world)
    pb = PlacedBuilding(
        instance_id=iid,
        blueprint_id=blueprint_id,
        plot_id=plot_key,
        grid_x=int(abs_gx),
        grid_y=int(abs_gy),
        built_at_tick=int(completes),
        built_by=str(party),
        status=status,
        efficiency_pct=100,
        missed_maintenance_cycles=0,
        due_at_tick=int(due),
        sub_plot_id=sub_plot_id,
        original_cost_cents=int(build_cost_cents),
        book_value_cents=int(build_cost_cents),
    )
    register_placed_building(world, pb)
    from realm.production.factory_design import consume_factory_machines_on_build

    mach = consume_factory_machines_on_build(world, party, blueprint_id)
    if not mach.get("ok"):
        return mach  # type: ignore[return-value]
    world.building_maintenance[iid] = {
        "due_at_tick": int(due),
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }

    if blueprint_id == "residence":
        from realm.population.towns import on_residence_built
        from realm.population.nascent_settlements import on_residence_built_nascent

        on_residence_built(world, plot_id)
        on_residence_built_nascent(world, plot_id)
    if blueprint_id == "store":
        from realm.population.stores import _register_store_with_town

        _register_store_with_town(world, plot_id)

    log_event(
        world,
        "blueprint_placed",
        f"{party} placed '{bp.name}' at {plot_id} ({abs_gx},{abs_gy})",
        party=str(party),
        plot_id=plot_key,
        blueprint_id=blueprint_id,
        instance_id=iid,
        grid_x=int(abs_gx),
        grid_y=int(abs_gy),
    )
    return {
        "ok": True,
        "instance_id": iid,
        "completes_at_tick": int(completes),
        "footprint": {
            "x": int(abs_gx),
            "y": int(abs_gy),
            "w": bp.footprint_w,
            "h": bp.footprint_h,
        },
    }


def place_road_path(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    cells: list[tuple[int, int]],
    build_mode: str = "turnkey",
) -> ActionResult:
    """Place ``road_segment`` on each cell in order; stops on first failure."""
    if not cells:
        return {"ok": False, "reason": "no cells"}
    placed: list[str] = []
    for gx, gy in cells:
        result = place_blueprint(
            world,
            party,
            plot_id,
            "road_segment",
            int(gx),
            int(gy),
            build_mode,
        )
        if not result.get("ok"):
            partial: ActionResult = {
                "ok": False,
                "reason": str(result.get("reason", "placement failed")),
                "placed_count": len(placed),
                "instance_ids": placed,
            }
            return partial
        placed.append(str(result.get("instance_id", "")))
    return {"ok": True, "placed_count": len(placed), "instance_ids": placed}


def build_on_plot(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    building_id: str,
    build_mode: str | None = None,
    construction_order_id: str | None = None,
) -> ActionResult:
    """Auto-place a seeded (or known) blueprint — for NPCs/scripts, not the player build UI."""
    if construction_order_id is not None:
        from realm.actions.construction_actions import (
            validate_construction_order_for_contractor_build,
        )

        ok_co, reason_co = validate_construction_order_for_contractor_build(
            world, party, plot_id, building_id, construction_order_id
        )
        if not ok_co:
            return {"ok": False, "reason": reason_co or "invalid construction order"}
    if building_id not in world.blueprints and building_id in BUILDINGS:
        from realm.production.blueprints import seed_world_blueprints

        seed_world_blueprints(world)
    bp = world.blueprints.get(building_id)
    if bp is None:
        return {"ok": False, "reason": f"unknown blueprint '{building_id}'"}
    pos = _find_free_position(world, str(plot_id), bp)
    if pos is None:
        return {"ok": False, "reason": "no free grid space on plot for this footprint"}
    gx, gy = pos
    mode = build_mode or "turnkey"
    if mode == "self_build":
        mode = "self"
    return place_blueprint(
        world,
        party,
        plot_id,
        building_id,
        gx,
        gy,
        build_mode=mode,
    )


def blueprints_visible_to(world: World, party: PartyId | None) -> list[dict]:
    out: list[dict] = []
    for bp in world.blueprints.values():
        if bp.is_public or bp.is_seeded:
            row = blueprint_public_dict(bp)
            row.update(turnkey_cost_public(world, bp))
            out.append(row)
        elif party is not None and bp.creator_party == str(party):
            row = blueprint_public_dict(bp)
            row.update(turnkey_cost_public(world, bp))
            out.append(row)
    out.sort(key=lambda r: str(r.get("blueprint_id", "")))
    return out


def plot_grid_state(world: World, plot_id: PlotId) -> dict:
    pid = str(plot_id)
    plot = world.plots.get(plot_id)
    grid_w, grid_h = plot_grid_side_for_id(world, plot_id)
    deed_cells: set[tuple[int, int]] = plot_deed_grid_cells(plot) if plot is not None else set()
    occupied: list[list[int]] = []
    free_cells = len(deed_cells) if deed_cells else grid_w * grid_h
    placed: list[dict] = []
    for iid in world.plot_placed_buildings.get(pid, []):
        pb = world.placed_buildings.get(iid)
        if pb is None:
            continue
        bp = world.blueprints.get(pb.blueprint_id)
        fw = bp.footprint_w if bp else 1
        fh = bp.footprint_h if bp else 1
        occupied.append([pb.grid_x, pb.grid_y, fw, fh])
        for cell in cells_occupied(pb.grid_x, pb.grid_y, fw, fh):
            if cell in deed_cells:
                free_cells -= 1
        placed.append(
            {
                "instance_id": pb.instance_id,
                "blueprint_id": pb.blueprint_id,
                "blueprint_name": bp.name if bp else pb.blueprint_id,
                "grid_x": pb.grid_x,
                "grid_y": pb.grid_y,
                "footprint_w": fw,
                "footprint_h": fh,
                "status": pb.status,
                "efficiency_pct": pb.efficiency_pct,
                "maintenance_due_in_ticks": max(0, pb.due_at_tick - world.tick),
            }
        )
    world_w = 1
    world_h = 1
    area_sq_m = 10_000
    if plot is not None:
        from realm.world.plot_scale import plot_area_sq_metres, plot_world_span

        _, _, world_w, world_h = plot_world_span(plot)
        area_sq_m = plot_area_sq_metres(plot)
    from realm.infrastructure.road_connectivity import (
        is_road_accessible,
        plot_site_roads_connect_workshops,
        plot_site_roads_link_world,
        plot_world_link_edges,
    )
    from realm.production.recipe_sites import plot_is_coastal, waterfront_build_cells

    waterfront: list[str] = []
    if plot is not None:
        waterfront = [
            f"{gx},{gy}" for gx, gy in sorted(waterfront_build_cells(world, plot))
        ]

    return {
        "grid_cells_w": grid_w,
        "grid_cells_h": grid_h,
        "cells_per_side": grid_w,
        "cell_side_metres": 10,
        "world_tiles_w": world_w,
        "world_tiles_h": world_h,
        "area_sq_metres": area_sq_m,
        "occupied_cells": occupied,
        "free_cells_count": max(0, free_cells),
        "placed_buildings": placed,
        "road_accessible": is_road_accessible(world, plot_id),
        "site_roads_connect_workshops": plot_site_roads_connect_workshops(world, plot_id),
        "site_roads_link_world": plot_site_roads_link_world(world, plot_id),
        "world_link_edges": plot_world_link_edges(world, plot_id),
        "is_coastal": plot_is_coastal(world, plot) if plot is not None else False,
        "waterfront_cells": waterfront,
    }


def demolish_building(world: World, party: PartyId, instance_id: str) -> ActionResult:
    """Remove a building; pay 50% of current book value as salvage from system reserve."""
    pb = world.placed_buildings.get(instance_id)
    if pb is None:
        return {"ok": False, "reason": "building not found"}
    if str(pb.built_by) != str(party):
        return {"ok": False, "reason": "not your building"}
    salvage = int(int(pb.book_value_cents) * 0.5)
    if salvage > 0:
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=party_cash_account(party),
            amount_cents=salvage,
        )
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
    plot_key = str(pb.plot_id)
    del world.placed_buildings[instance_id]
    iids = world.plot_placed_buildings.get(plot_key, [])
    if instance_id in iids:
        iids.remove(instance_id)
    world.building_maintenance.pop(instance_id, None)
    sync_plot_buildings_from_placed(world)
    log_event(
        world,
        "building_demolished",
        (
            f"{party} demolished {pb.blueprint_id} at {pb.plot_id} "
            f"(salvage: {salvage}¢)"
        ),
        party=str(party),
        salvage_cents=salvage,
        instance_id=instance_id,
    )
    return {"ok": True, "salvage_cents": salvage}


def available_positions(
    world: World, plot_id: PlotId, blueprint_id: str
) -> list[dict[str, int]]:
    bp = world.blueprints.get(blueprint_id)
    if bp is None:
        return []
    plot = world.plots.get(plot_id)
    gw, gh = plot_grid_side_for_id(world, plot_id)
    out: list[dict[str, int]] = []
    for gy in range(gh):
        for gx in range(gw):
            if not cells_free(str(plot_id), world, gx, gy, bp.footprint_w, bp.footprint_h):
                continue
            if bp.requires_coastal and plot is not None:
                from realm.production.recipe_sites import footprint_borders_water

                if not footprint_borders_water(
                    world, plot, gx, gy, bp.footprint_w, bp.footprint_h
                ):
                    continue
            out.append({"grid_x": gx, "grid_y": gy})
    return out

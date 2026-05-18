"""Blueprint registration and placement on plot grids."""

from __future__ import annotations

from realm.actions._shared import ActionResult
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import BUILD_CONTRACTED_TICKS, BUILD_SIMPLE_TICKS
from realm.economy.markets import market_buy
from realm.events.event_log import log_event
from realm.production.blueprints import Blueprint, blueprint_public_dict
from realm.production.buildings import BUILDINGS
from realm.production.recipes import RECIPES
from realm.world import World
from realm.world.placed_buildings import PlacedBuilding, register_placed_building
from realm.world.plot_scale import (
    cells_free,
    cells_occupied,
    plot_deed_grid_cells,
    plot_grid_side_for_id,
)


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
    custom = world.scenario_state.get("custom_recipes") or {}
    for recipe_id in enabled_recipe_ids:
        if recipe_id not in RECIPES and recipe_id not in custom:
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
        from realm.production.recipe_sites import plot_is_coastal

        if not plot_is_coastal(world, plot):
            return {"ok": False, "reason": "requires coastal terrain"}
    if bp.requires_power:
        powered = world.scenario_state.get("powered_plots") or set()
        if plot_key not in powered:
            return {"ok": False, "reason": "plot is not within power grid range"}

    if not cells_free(plot_key, world, abs_gx, abs_gy, bp.footprint_w, bp.footprint_h):
        return {
            "ok": False,
            "reason": "grid position overlaps an existing building or is out of bounds",
        }

    mode = build_mode
    if mode == "self_contract":
        mode = "self"

    if mode == "turnkey":
        turnkey_cost = bp.construction_labor_cents
        for mat_id, qty in bp.construction_materials.items():
            asks = world.market_asks_by_material.get(mat_id, [])
            if asks:
                best = min(int(a.price_per_unit_cents) for a in asks)
                turnkey_cost += best * int(qty)
            else:
                turnkey_cost += 999_999 * int(qty)
        cash = party_cash_account(party)
        if world.ledger.balance(cash) < turnkey_cost:
            return {"ok": False, "reason": f"need ${turnkey_cost / 100:.2f} for turnkey build"}
        if bp.construction_labor_cents > 0:
            tr = world.ledger.transfer(
                debit=cash,
                credit=system_reserve_account(),
                amount_cents=bp.construction_labor_cents,
            )
            if isinstance(tr, MoneyErr):
                return {"ok": False, "reason": tr.reason}
        for mat_id, qty in bp.construction_materials.items():
            if int(qty) <= 0:
                continue
            br = market_buy(
                world,
                party,
                MaterialId(mat_id),
                int(qty),
                max_price_per_unit_cents=999_999,
            )
            if not br.get("ok"):
                return {"ok": False, "reason": str(br.get("reason", "market buy failed"))}
    elif mode == "self":
        for mat_id, qty in bp.construction_materials.items():
            have = world.inventory.qty(party, MaterialId(mat_id))
            if have < int(qty):
                return {"ok": False, "reason": f"missing {mat_id}: need {qty}, have {have}"}
        for mat_id, qty in bp.construction_materials.items():
            rm = world.inventory.remove(party, MaterialId(mat_id), int(qty))
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
    )
    register_placed_building(world, pb)
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
            out.append(blueprint_public_dict(bp))
        elif party is not None and bp.creator_party == str(party):
            out.append(blueprint_public_dict(bp))
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
    }


def available_positions(
    world: World, plot_id: PlotId, blueprint_id: str
) -> list[dict[str, int]]:
    bp = world.blueprints.get(blueprint_id)
    if bp is None:
        return []
    gw, gh = plot_grid_side_for_id(world, plot_id)
    out: list[dict[str, int]] = []
    for gy in range(gh):
        for gx in range(gw):
            if cells_free(str(plot_id), world, gx, gy, bp.footprint_w, bp.footprint_h):
                out.append({"grid_x": gx, "grid_y": gy})
    return out

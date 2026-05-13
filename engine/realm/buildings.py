"""Plot buildings — cash + (for workshops) contractor paths: self-supply vs turnkey procurement."""

from __future__ import annotations

from typing import Any

from realm.decay import BUILDING_CONDITION_FULL_BPS
from realm.event_log import log_event
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.time_scale import BUILD_CONTRACTED_TICKS, BUILD_SIMPLE_TICKS
from realm.world import World

# ``kind``:
# - ``simple``: single ``cost_cents`` cash to reserve (legacy sheds).
# - ``contracted``: self path pays shell + contractor fee + removes ``self_materials`` from player;
#   turnkey pays ``turnkey_total_cents`` **and** removes the same ``self_materials`` from the
#   builder's inventory (site must be stocked before the contractor fee is charged).
BUILDINGS: dict[str, dict[str, Any]] = {
    "field_stockade": {
        "kind": "simple",
        "label": "Field stockade (+5k storage units)",
        "cost_cents": 25_000,
    },
    "tool_cache": {
        "kind": "simple",
        "label": "Tool cache (−10% recipe labor cash on this plot)",
        "cost_cents": 50_000,
    },
    "watch_hut": {
        "kind": "simple",
        "label": "Watch hut (−3% recipe labor cash on this plot)",
        "cost_cents": 15_000,
    },
    "power_shed": {
        "kind": "contracted",
        "label": "Power shed (generator pad + intertie)",
        "self_shell_cents": 30_000,
        "self_contractor_fee_cents": 12_000,
        "self_materials": {"timber": 4, "lumber": 2},
        "turnkey_total_cents": 78_000,
        "maintenance_schedule": {
            "interval_ticks": 5_760,  # 4 game-days
            "materials": {"coal": 2, "timber": 1},
            "grace_ticks": 720,  # 12 hours
        },
    },
    "wood_shop": {
        "kind": "contracted",
        "label": "Wood shop (saw line, cordage bench, charcoal retort)",
        "self_shell_cents": 48_000,
        "self_contractor_fee_cents": 20_000,
        "self_materials": {"timber": 6, "lumber": 2, "coal": 2},
        "turnkey_total_cents": 118_000,
        "maintenance_schedule": {
            "interval_ticks": 8_640,  # 6 game-days
            "materials": {"lumber": 1, "coal": 1},
            "grace_ticks": 1_440,
        },
    },
    "foundry": {
        "kind": "contracted",
        "label": "Foundry (smelt, steel, wire draw)",
        "self_shell_cents": 95_000,
        "self_contractor_fee_cents": 42_000,
        "self_materials": {"brick": 6, "stone": 4, "coal": 4},
        "turnkey_total_cents": 215_000,
        "maintenance_schedule": {
            "interval_ticks": 10_080,  # 7 game-days
            "materials": {"brick": 2, "coal": 2},
            "grace_ticks": 2_880,  # 2 game-days
        },
    },
    "kiln_shed": {
        "kind": "contracted",
        "label": "Kiln shed (brick + pottery)",
        "self_shell_cents": 55_000,
        "self_contractor_fee_cents": 22_000,
        "self_materials": {"clay": 8, "brick": 2, "coal": 2},
        "turnkey_total_cents": 128_000,
        "maintenance_schedule": {
            "interval_ticks": 7_200,  # 5 game-days
            "materials": {"clay": 3, "coal": 1},
            "grace_ticks": 1_440,
        },
    },
    "stone_works": {
        "kind": "contracted",
        "label": "Stone works (crush, lime, mortar, glass)",
        "self_shell_cents": 50_000,
        "self_contractor_fee_cents": 20_000,
        "self_materials": {"stone": 6, "timber": 3, "coal": 2},
        "turnkey_total_cents": 112_000,
        "maintenance_schedule": {
            "interval_ticks": 10_080,  # 7 game-days
            "materials": {"stone": 2, "coal": 1},
            "grace_ticks": 2_880,
        },
    },
    "gristmill": {
        "kind": "contracted",
        "label": "Gristmill & bakehouse",
        "self_shell_cents": 40_000,
        "self_contractor_fee_cents": 16_000,
        "self_materials": {"grain": 6, "lumber": 2, "brick": 2},
        "turnkey_total_cents": 96_000,
        "maintenance_schedule": {
            "interval_ticks": 8_640,  # 6 game-days
            "materials": {"timber": 1, "brick": 1},
            "grace_ticks": 1_440,
        },
    },
    "strip_mine": {
        "kind": "contracted",
        "label": "Strip mine & clay pit (ore, coal, clay extraction)",
        "self_shell_cents": 62_000,
        "self_contractor_fee_cents": 28_000,
        "self_materials": {"timber": 8, "brick": 4, "coal": 3},
        "turnkey_total_cents": 142_000,
        "maintenance_schedule": {
            "interval_ticks": 7_200,  # 5 game-days
            "materials": {"timber": 2, "rope": 1},
            "grace_ticks": 1_440,
        },
    },
    "timber_yard": {
        "kind": "contracted",
        "label": "Timber yard (fell & skid)",
        "self_shell_cents": 28_000,
        "self_contractor_fee_cents": 11_000,
        "self_materials": {"timber": 4, "lumber": 2},
        "turnkey_total_cents": 68_000,
        "maintenance_schedule": {
            "interval_ticks": 7_200,  # 5 game-days
            "materials": {"lumber": 1},
            "grace_ticks": 1_440,
        },
    },
    "grain_row": {
        "kind": "contracted",
        "label": "Irrigated grain row",
        "self_shell_cents": 32_000,
        "self_contractor_fee_cents": 12_000,
        "self_materials": {"grain": 4, "lumber": 3, "brick": 2},
        "turnkey_total_cents": 78_000,
        "maintenance_schedule": {
            "interval_ticks": 5_760,  # 4 game-days
            "materials": {"grain": 2, "timber": 1},
            "grace_ticks": 720,
        },
    },
    "assay_lab": {
        "kind": "contracted",
        "label": "Assay laboratory (mineral analysis & recipe discovery)",
        "self_shell_cents": 45_000,
        "self_contractor_fee_cents": 18_000,
        "self_materials": {"brick": 4, "timber": 2, "coal": 2, "glass": 2},
        "turnkey_total_cents": 110_000,
    },
    "blast_furnace": {
        "kind": "contracted",
        "label": "Blast furnace (large-scale iron smelting, pig iron)",
        "self_shell_cents": 380_000,
        "self_contractor_fee_cents": 120_000,
        "self_materials": {"brick": 24, "stone": 16, "coal": 12, "iron_ingot": 4},
        "turnkey_total_cents": 680_000,
    },
    "chemical_works": {
        "kind": "contracted",
        "label": "Chemical works (sulfur, saltpeter, acids, phosphate)",
        "self_shell_cents": 140_000,
        "self_contractor_fee_cents": 55_000,
        "self_materials": {"brick": 12, "stone": 6, "glass": 4, "lumber": 4, "coal": 3},
        "turnkey_total_cents": 310_000,
    },
    "forge_press": {
        "kind": "contracted",
        "label": "Forge & press (metal tool components, drill bits)",
        "self_shell_cents": 120_000,
        "self_contractor_fee_cents": 45_000,
        "self_materials": {"brick": 10, "stone": 4, "iron_ingot": 6, "coal": 4},
        "turnkey_total_cents": 250_000,
    },
    "machine_shop": {
        "kind": "contracted",
        "label": "Machine shop (pumps, gears, industrial equipment)",
        "self_shell_cents": 200_000,
        "self_contractor_fee_cents": 80_000,
        "self_materials": {"brick": 14, "stone": 6, "iron_ingot": 8, "copper_wire": 4, "coal": 5},
        "turnkey_total_cents": 480_000,
    },
    "tool_workshop": {
        "kind": "contracted",
        "label": "Tool workshop (assemble mining picks, saws, axes)",
        "self_shell_cents": 80_000,
        "self_contractor_fee_cents": 32_000,
        "self_materials": {"lumber": 6, "brick": 4, "iron_ingot": 4, "coal": 2},
        "turnkey_total_cents": 195_000,
    },
    "drill_rig": {
        "kind": "contracted",
        "label": "Drill rig (deep geological survey for rare minerals)",
        "self_shell_cents": 280_000,
        "self_contractor_fee_cents": 90_000,
        "self_materials": {
            "steel_ingot": 8,
            "cast_iron": 4,
            "lumber": 6,
            "rope": 4,
            "pump_unit": 1,
        },
        "turnkey_total_cents": 580_000,
    },
    # ───────── Shipping infrastructure (Sprint 2 — route operators) ─────────
    "dock": {
        "kind": "contracted",
        "label": "Coastal dock (vessel operations + coastal route registration)",
        "self_shell_cents": 85_000,
        "self_contractor_fee_cents": 28_000,
        "self_materials": {"timber": 10, "lumber": 4, "rope": 3, "stone": 2},
        "turnkey_total_cents": 185_000,
        "terrain_required": ("coastal",),
        "maintenance_schedule": {
            "interval_ticks": 7_200,  # 5 game-days
            "materials": {"timber": 2, "rope": 1},
            "grace_ticks": 1_440,
        },
    },
    "waystation": {
        "kind": "contracted",
        "label": "Inland waystation (route operations on inland regions)",
        "self_shell_cents": 40_000,
        "self_contractor_fee_cents": 15_000,
        "self_materials": {"timber": 6, "lumber": 2, "brick": 2},
        "turnkey_total_cents": 90_000,
        "maintenance_schedule": {
            "interval_ticks": 8_640,  # 6 game-days
            "materials": {"timber": 1, "brick": 1},
            "grace_ticks": 1_440,
        },
    },
}


def building_catalog_public() -> list[dict]:
    out: list[dict] = []
    for bid, spec in sorted(BUILDINGS.items(), key=lambda x: x[0]):
        kind = str(spec.get("kind", "simple"))
        if kind == "simple":
            out.append(
                {
                    "id": bid,
                    "label": str(spec["label"]),
                    "kind": "simple",
                    "cost_cents": int(spec["cost_cents"]),
                }
            )
        elif kind == "contracted":
            mats = spec.get("self_materials") or {}
            row: dict[str, Any] = {
                "id": bid,
                "label": str(spec["label"]),
                "kind": "contracted",
                "self_shell_cents": int(spec["self_shell_cents"]),
                "self_contractor_fee_cents": int(spec["self_contractor_fee_cents"]),
                "self_materials": {str(k): int(v) for k, v in mats.items()},
                "turnkey_total_cents": int(spec["turnkey_total_cents"]),
            }
            sched = spec.get("maintenance_schedule")
            if isinstance(sched, dict):
                row["maintenance_schedule"] = {
                    "interval_ticks": int(sched.get("interval_ticks", 0)),
                    "grace_ticks": int(sched.get("grace_ticks", 0)),
                    "materials": {
                        str(k): int(v) for k, v in (sched.get("materials") or {}).items()
                    },
                }
            terrain_req = spec.get("terrain_required")
            if terrain_req:
                row["terrain_required"] = (
                    list(terrain_req) if not isinstance(terrain_req, str) else [terrain_req]
                )
            out.append(row)
    return out


def build_on_plot(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    building_id: str,
    build_mode: str | None = None,
) -> dict:
    """
    Place a structure: simple buildings pay ``cost_cents``; contracted workshops need
    ``build_mode`` ∈ {``self_contract``, ``turnkey``}.
    """
    spec = BUILDINGS.get(building_id)
    if spec is None:
        return {"ok": False, "reason": "unknown building"}
    kind = str(spec.get("kind", "simple"))
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    terrain_req = spec.get("terrain_required")
    if terrain_req:
        req_tuple = (terrain_req,) if isinstance(terrain_req, str) else tuple(terrain_req)
        req_names = tuple(str(t) for t in req_tuple)
        if "coastal" in req_names:
            from realm.recipe_sites import plot_is_coastal

            allowed = plot_is_coastal(world, plot)
        else:
            allowed = plot.terrain.value in req_names
        if not allowed:
            return {
                "ok": False,
                "reason": f"{building_id} requires terrain in {sorted(req_names)} (plot is {plot.terrain.value})",
            }
    cash = party_cash_account(party)
    label = str(spec["label"])
    total_cents: int
    mode_out: str

    if kind == "simple":
        total_cents = int(spec["cost_cents"])
        mode_out = "simple"
        if world.ledger.balance(cash) < total_cents:
            return {"ok": False, "reason": "insufficient cash"}
    else:
        if build_mode not in ("self_contract", "turnkey"):
            return {"ok": False, "reason": "build_mode required: self_contract or turnkey"}
        shell = int(spec["self_shell_cents"])
        fee = int(spec["self_contractor_fee_cents"])
        mats_raw = spec.get("self_materials") or {}
        mats: dict[str, int] = {str(k): int(v) for k, v in mats_raw.items()}
        turnkey = int(spec["turnkey_total_cents"])
        if build_mode == "turnkey":
            # Turnkey: same physical ``self_materials`` must leave the builder's inventory before
            # the turnkey cash fee (site is stocked; the fee covers labour / contractor margin).
            total_cents = turnkey
            mode_out = "turnkey"
            if world.ledger.balance(cash) < total_cents:
                return {"ok": False, "reason": "insufficient cash"}
            for mid_s, qty in mats.items():
                mid = MaterialId(mid_s)
                have = world.inventory.qty(party, mid)
                if have < qty:
                    return {
                        "ok": False,
                        "reason": f"missing material: {mid_s} (need {qty}, have {have})",
                    }
            for mid_s, qty in mats.items():
                mid = MaterialId(mid_s)
                rm = world.inventory.remove(party, mid, int(qty))
                if isinstance(rm, MatterErr):
                    return {"ok": False, "reason": rm.reason}
        else:
            total_cents = shell + fee
            mode_out = "self_contract"
            if world.ledger.balance(cash) < total_cents:
                return {"ok": False, "reason": "insufficient cash"}
            for mid_s, qty in mats.items():
                mid = MaterialId(mid_s)
                if world.inventory.qty(party, mid) < qty:
                    return {"ok": False, "reason": f"insufficient {mid_s} for contractor build"}
            for mid_s, qty in mats.items():
                mid = MaterialId(mid_s)
                rm = world.inventory.remove(party, mid, qty)
                if isinstance(rm, MatterErr):
                    return {"ok": False, "reason": rm.reason}

    pay = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=total_cents,
    )
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}
    world.next_building_instance_seq += 1
    instance_id = f"b{world.next_building_instance_seq:06d}"
    completes_at = world.tick + (BUILD_SIMPLE_TICKS if kind == "simple" else BUILD_CONTRACTED_TICKS)
    world.plot_buildings.append(
        {
            "instance_id": instance_id,
            "condition_bps": BUILDING_CONDITION_FULL_BPS,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": building_id,
            "label": label,
            "cost_cents": total_cents,
            "build_mode": mode_out,
            "completes_at_tick": int(completes_at),
        }
    )
    # Initialise the maintenance record for buildings with a schedule. First window
    # opens one full ``interval`` after the building becomes operational.
    sched = spec.get("maintenance_schedule")
    if isinstance(sched, dict):
        interval = max(1, int(sched.get("interval_ticks", 0)))
        world.building_maintenance[instance_id] = {
            "due_at_tick": int(completes_at) + interval,
            "missed_cycles": 0,
            "efficiency_pct": 100,
        }
    log_event(
        world,
        "build",
        f"{party} built {label} on {plot_id} ({mode_out}) for ${total_cents / 100:.2f}",
        party=str(party),
        plot_id=str(plot_id),
        building_id=building_id,
        cost_cents=total_cents,
        build_mode=mode_out,
    )
    return {
        "ok": True,
        "building_id": building_id,
        "instance_id": instance_id,
        "build_mode": mode_out,
        "completes_at_tick": int(completes_at),
    }

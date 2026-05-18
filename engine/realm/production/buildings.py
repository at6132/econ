"""Plot buildings — cash + (for workshops) contractor paths: self-supply vs turnkey procurement."""

from __future__ import annotations

from typing import Any

from realm.production.decay import BUILDING_CONDITION_FULL_BPS
from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import BUILD_CONTRACTED_TICKS, BUILD_SIMPLE_TICKS
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
    "bank_building": {
        "kind": "simple",
        "label": "First Bank of the Frontier",
        "cost_cents": 0,
    },
    "road_segment": {
        "kind": "simple",
        "label": "Road segment (connects to adjacent plot — reduces movement cost)",
        "cost_cents": 12_000,
        "material_inputs": {"lumber": 2, "stone": 2},
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
    # Phase 7C — residential building. Laborers live here; meets their
    # shelter need. Up to 8 occupants per residence. Three residences within
    # 5 tiles of one another form a town (see realm/towns.py).
    "residence": {
        "kind": "contracted",
        "label": "Residential building (houses up to 8 laborers)",
        "self_shell_cents": 60_000,
        "self_contractor_fee_cents": 20_000,
        "self_materials": {"lumber": 8, "brick": 6, "timber": 4},
        "turnkey_total_cents": 140_000,
        "capacity": 8,
    },
    # Phase 7D — store. Sells goods to laborers in the surrounding town.
    # Inventory + prices are tracked separately in ``world.store_inventories``
    # and ``world.store_prices``; ``tick_laborer_spending`` drains stock as
    # laborers buy food / fuel each game-day.
    "store": {
        "kind": "contracted",
        "label": "General store (sell goods to town laborers)",
        "self_shell_cents": 45_000,
        "self_contractor_fee_cents": 18_000,
        "self_materials": {"lumber": 6, "timber": 4, "brick": 2},
        "turnkey_total_cents": 95_000,
    },
    # Phase 8C — apothecary. Converts wild_herb + coal + electricity into
    # medicine. Outside of epidemics medicine has near-zero demand; during
    # an epidemic it becomes the most valuable good on the affected island.
    "apothecary": {
        "kind": "contracted",
        "label": "Apothecary (produces medicine from wild herbs)",
        "self_shell_cents": 55_000,
        "self_contractor_fee_cents": 22_000,
        "self_materials": {"lumber": 4, "brick": 2, "glass": 2, "timber": 2},
        "turnkey_total_cents": 120_000,
    },
    "laboratory": {
        "kind": "contracted",
        "label": "Laboratory (chemistry experiments)",
        "self_shell_cents": 70_000,
        "self_contractor_fee_cents": 28_000,
        "self_materials": {"lumber": 4, "brick": 4, "glass": 4, "timber": 2},
        "turnkey_total_cents": 150_000,
        "labor_days": 4,
    },
    # Phase 9A — Shipyard. Coastal-only; runs the build_cargo_vessel recipe.
    # Without a shipyard the only path to vessels is the bootstrap stockpile
    # at genesis_exchange (Sprint 2 seeded 20 vessels) — a real economy needs
    # a way to manufacture them. Steel + lumber + rope + pump_unit.
    "shipyard": {
        "kind": "contracted",
        "label": "Shipyard (coastal — builds cargo vessels)",
        "self_shell_cents": 220_000,
        "self_contractor_fee_cents": 60_000,
        "self_materials": {
            "lumber": 16,
            "timber": 10,
            "rope": 6,
            "brick": 8,
            "iron_ingot": 4,
        },
        "turnkey_total_cents": 360_000,
        "terrain_required": ("coastal",),
        "maintenance_schedule": {
            "interval_ticks": 10_080,  # 7 game-days
            "materials": {"lumber": 2, "rope": 1},
            "grace_ticks": 2_880,
        },
    },
    # Sprint 3 — Phase D.4: coastal renewable power. Half the throughput of a
    # coal power_shed but zero ongoing fuel cost.
    "tidal_mill": {
        "kind": "contracted",
        "label": "Tidal mill (coastal renewable electricity — no coal needed)",
        "self_shell_cents": 120_000,
        "self_contractor_fee_cents": 40_000,
        "self_materials": {"timber": 12, "rope": 4, "stone": 6, "lumber": 4},
        "turnkey_total_cents": 260_000,
        "terrain_required": ("coastal",),
        "maintenance_schedule": {
            "interval_ticks": 7_200,  # 5 game-days
            "materials": {"timber": 2, "rope": 1},
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
            cap = spec.get("capacity")
            if cap is not None:
                row["capacity"] = int(cap)
            out.append(row)
    return out


def build_on_plot(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    building_id: str,
    build_mode: str | None = None,
    construction_order_id: str | None = None,
) -> dict:
    """Auto-place a blueprint on the plot grid (NPCs/scripts — players use ``place_blueprint``)."""
    from realm.actions.blueprint_actions import build_on_plot as _bp_build

    return _bp_build(
        world,
        party,
        plot_id,
        building_id,
        build_mode,
        construction_order_id,
    )

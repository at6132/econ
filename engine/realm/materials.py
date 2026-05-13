"""Starter material catalog (Primitive 2) — v1 uses named real materials per spec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

from realm.ids import MaterialId
from realm.time_scale import legacy_scaled


@dataclass(frozen=True, slots=True)
class MaterialDef:
    material_id: MaterialId
    display_name: str
    mass_per_unit_kg: float
    category: str  # ore, organic, processed, energy, construction, tool
    spoils_to: MaterialId | None = None
    spoilage_interval_ticks: int = 0  # 0 = disabled; checked as tick % interval == 0
    durable: bool = False  # tools / capital goods — no organic spoilage path in v1


# Phase 1–2 catalog: construction + ores + organics + industry chain (slag models process waste).
MATERIALS: Final[Mapping[MaterialId, MaterialDef]] = {
    MaterialId("timber"): MaterialDef(
        MaterialId("timber"), "Timber", 450.0, "construction"
    ),
    MaterialId("lumber"): MaterialDef(
        MaterialId("lumber"), "Lumber", 400.0, "construction"
    ),
    MaterialId("iron_ore"): MaterialDef(
        MaterialId("iron_ore"), "Iron ore", 5000.0, "ore"
    ),
    MaterialId("iron_ingot"): MaterialDef(
        MaterialId("iron_ingot"), "Iron ingot", 7850.0, "processed"
    ),
    MaterialId("copper_ore"): MaterialDef(
        MaterialId("copper_ore"), "Copper ore", 4200.0, "ore"
    ),
    MaterialId("copper_ingot"): MaterialDef(
        MaterialId("copper_ingot"), "Copper ingot", 8960.0, "processed"
    ),
    MaterialId("clay"): MaterialDef(MaterialId("clay"), "Clay", 1800.0, "construction"),
    MaterialId("grain"): MaterialDef(
        MaterialId("grain"),
        "Grain",
        780.0,
        "organic",
        spoils_to=MaterialId("spoiled_grain"),
        spoilage_interval_ticks=legacy_scaled(10),
    ),
    MaterialId("spoiled_grain"): MaterialDef(
        MaterialId("spoiled_grain"), "Spoiled grain", 780.0, "organic"
    ),
    MaterialId("coal"): MaterialDef(MaterialId("coal"), "Coal", 1300.0, "energy"),
    # Electricity dissipates if held off-grid too long (Sprint 3 — Phase A.2).
    # 480 ticks ≈ 8 game-hours; staged shipments must be consumed quickly.
    MaterialId("electricity"): MaterialDef(
        MaterialId("electricity"),
        "Electricity (MWh)",
        0.0,
        "energy",
        spoils_to=MaterialId("dissipated_energy"),
        spoilage_interval_ticks=480,
    ),
    MaterialId("dissipated_energy"): MaterialDef(
        MaterialId("dissipated_energy"), "Dissipated energy", 0.0, "energy"
    ),
    MaterialId("brick"): MaterialDef(
        MaterialId("brick"), "Fired brick", 1900.0, "construction"
    ),
    MaterialId("stone"): MaterialDef(MaterialId("stone"), "Crushed stone", 2600.0, "construction"),
    MaterialId("sand"): MaterialDef(MaterialId("sand"), "Sand", 1600.0, "construction"),
    MaterialId("limestone"): MaterialDef(
        MaterialId("limestone"), "Limestone", 2700.0, "construction"
    ),
    MaterialId("quicklime"): MaterialDef(
        MaterialId("quicklime"), "Quicklime", 1200.0, "processed"
    ),
    MaterialId("mortar"): MaterialDef(MaterialId("mortar"), "Mortar mix", 2100.0, "construction"),
    MaterialId("glass"): MaterialDef(MaterialId("glass"), "Glass", 2500.0, "processed"),
    MaterialId("flour"): MaterialDef(MaterialId("flour"), "Flour", 600.0, "organic"),
    MaterialId("bread"): MaterialDef(
        MaterialId("bread"),
        "Bread",
        500.0,
        "organic",
        spoils_to=MaterialId("spoiled_grain"),
        spoilage_interval_ticks=legacy_scaled(14),
    ),
    MaterialId("steel_ingot"): MaterialDef(
        MaterialId("steel_ingot"), "Steel ingot", 7850.0, "processed"
    ),
    MaterialId("copper_wire"): MaterialDef(
        MaterialId("copper_wire"), "Copper wire", 8960.0, "processed"
    ),
    MaterialId("charcoal"): MaterialDef(
        MaterialId("charcoal"), "Charcoal", 400.0, "energy"
    ),
    MaterialId("pottery"): MaterialDef(
        MaterialId("pottery"), "Fired pottery", 2000.0, "construction"
    ),
    MaterialId("slag"): MaterialDef(
        MaterialId("slag"), "Slag / tailings", 2500.0, "processed"
    ),
    MaterialId("rope"): MaterialDef(
        MaterialId("rope"), "Cordage (rope)", 80.0, "construction"
    ),
    MaterialId("ladder"): MaterialDef(
        MaterialId("ladder"), "Timber ladder (assembled)", 120.0, "construction"
    ),
    MaterialId("pick_axe"): MaterialDef(
        MaterialId("pick_axe"), "Pick axe", 2.2, "tool", durable=True
    ),
    MaterialId("mining_pick"): MaterialDef(
        MaterialId("mining_pick"), "Mining pick", 3.5, "tool", durable=True
    ),
    MaterialId("spade"): MaterialDef(MaterialId("spade"), "Spade", 2.0, "tool", durable=True),
    MaterialId("hand_saw"): MaterialDef(
        MaterialId("hand_saw"), "Hand saw", 0.8, "tool", durable=True
    ),
    # ───────── Transport capital (durable; required for coastal route registration) ─────────
    MaterialId("vessel"): MaterialDef(
        MaterialId("vessel"), "Vessel (cargo)", 4800.0, "transport", durable=True
    ),
    # ───────── Tier-2 raw minerals (extracted; recipes locked behind assay discovery) ─────────
    MaterialId("sulfur_ore"): MaterialDef(
        MaterialId("sulfur_ore"), "Sulfur ore", 2100.0, "ore"
    ),
    MaterialId("saltpeter_ore"): MaterialDef(
        MaterialId("saltpeter_ore"), "Saltpeter ore", 2200.0, "ore"
    ),
    MaterialId("tin_ore"): MaterialDef(
        MaterialId("tin_ore"), "Tin ore", 6900.0, "ore"
    ),
    MaterialId("lead_ore"): MaterialDef(
        MaterialId("lead_ore"), "Lead ore", 7400.0, "ore"
    ),
    MaterialId("phosphate_ore"): MaterialDef(
        MaterialId("phosphate_ore"), "Phosphate ore", 3100.0, "ore"
    ),
    MaterialId("raw_silica"): MaterialDef(
        MaterialId("raw_silica"), "Raw silica", 2650.0, "ore"
    ),
    # ───────── Processed Tier-2 (chemical / metallurgical chains) ─────────
    MaterialId("pig_iron"): MaterialDef(
        MaterialId("pig_iron"), "Pig iron", 7200.0, "processed"
    ),
    MaterialId("cast_iron"): MaterialDef(
        MaterialId("cast_iron"), "Cast iron", 7300.0, "processed"
    ),
    MaterialId("bronze_ingot"): MaterialDef(
        MaterialId("bronze_ingot"), "Bronze ingot", 8800.0, "processed"
    ),
    MaterialId("tin_ingot"): MaterialDef(
        MaterialId("tin_ingot"), "Tin ingot", 7300.0, "processed"
    ),
    MaterialId("lead_ingot"): MaterialDef(
        MaterialId("lead_ingot"), "Lead ingot", 11340.0, "processed"
    ),
    MaterialId("sulfur_ore_refined"): MaterialDef(
        MaterialId("sulfur_ore_refined"), "Refined sulfur", 2050.0, "processed"
    ),
    MaterialId("sulfuric_acid"): MaterialDef(
        MaterialId("sulfuric_acid"), "Sulfuric acid", 1840.0, "processed"
    ),
    MaterialId("refined_saltpeter"): MaterialDef(
        MaterialId("refined_saltpeter"), "Refined saltpeter", 2100.0, "processed"
    ),
    MaterialId("gunpowder"): MaterialDef(
        MaterialId("gunpowder"), "Gunpowder", 1700.0, "processed"
    ),
    MaterialId("phosphate_meal"): MaterialDef(
        MaterialId("phosphate_meal"), "Phosphate meal", 2400.0, "processed"
    ),
    MaterialId("fused_silica"): MaterialDef(
        MaterialId("fused_silica"), "Fused silica", 2200.0, "processed"
    ),
    # ───────── Tool components (intermediate goods feeding tool_workshop) ─────────
    MaterialId("pick_head"): MaterialDef(
        MaterialId("pick_head"), "Pick head", 2.4, "processed"
    ),
    MaterialId("saw_blade"): MaterialDef(
        MaterialId("saw_blade"), "Saw blade", 0.6, "processed"
    ),
    MaterialId("drill_bit"): MaterialDef(
        MaterialId("drill_bit"), "Drill bit", 1.2, "processed"
    ),
    MaterialId("pump_unit"): MaterialDef(
        MaterialId("pump_unit"), "Pump unit", 22.0, "processed"
    ),
    MaterialId("gear_set"): MaterialDef(
        MaterialId("gear_set"), "Gear set", 8.5, "processed"
    ),
    # ───────── Tier-3 ultra-rare minerals (revealed only via deep_survey) ─────────
    MaterialId("platinum_ore"): MaterialDef(
        MaterialId("platinum_ore"), "Platinum ore", 5400.0, "ore"
    ),
    MaterialId("oil_shale"): MaterialDef(
        MaterialId("oil_shale"), "Oil shale", 2400.0, "ore"
    ),
    MaterialId("rare_earth_ore"): MaterialDef(
        MaterialId("rare_earth_ore"), "Rare earth ore", 4200.0, "ore"
    ),
    MaterialId("refined_platinum"): MaterialDef(
        MaterialId("refined_platinum"), "Refined platinum", 21450.0, "processed"
    ),
    MaterialId("shale_oil"): MaterialDef(
        MaterialId("shale_oil"), "Shale oil", 870.0, "processed"
    ),
}

DURABLE_MATERIAL_IDS: frozenset[MaterialId] = frozenset(
    mid for mid, mdef in MATERIALS.items() if mdef.durable
)


def all_material_ids() -> tuple[MaterialId, ...]:
    return tuple(MATERIALS.keys())

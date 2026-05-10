"""Starter material catalog (Primitive 2) — v1 uses named real materials per spec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

from realm.ids import MaterialId


@dataclass(frozen=True, slots=True)
class MaterialDef:
    material_id: MaterialId
    display_name: str
    mass_per_unit_kg: float
    category: str  # ore, organic, processed, energy, construction
    spoils_to: MaterialId | None = None
    spoilage_interval_ticks: int = 0  # 0 = disabled; checked as tick % interval == 0


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
        spoilage_interval_ticks=10,
    ),
    MaterialId("spoiled_grain"): MaterialDef(
        MaterialId("spoiled_grain"), "Spoiled grain", 780.0, "organic"
    ),
    MaterialId("coal"): MaterialDef(MaterialId("coal"), "Coal", 1300.0, "energy"),
    MaterialId("electricity"): MaterialDef(
        MaterialId("electricity"), "Electricity (MWh)", 0.0, "energy"
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
        spoilage_interval_ticks=14,
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
}


def all_material_ids() -> tuple[MaterialId, ...]:
    return tuple(MATERIALS.keys())

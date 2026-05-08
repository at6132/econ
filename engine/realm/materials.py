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


# ~10 starter materials for Phase 1 prototype
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
    MaterialId("grain"): MaterialDef(MaterialId("grain"), "Grain", 780.0, "organic"),
    MaterialId("coal"): MaterialDef(MaterialId("coal"), "Coal", 1300.0, "energy"),
    MaterialId("electricity"): MaterialDef(
        MaterialId("electricity"), "Electricity (MWh)", 0.0, "energy"
    ),
    MaterialId("brick"): MaterialDef(
        MaterialId("brick"), "Fired brick", 1900.0, "construction"
    ),
}


def all_material_ids() -> tuple[MaterialId, ...]:
    return tuple(MATERIALS.keys())

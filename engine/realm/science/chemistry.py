"""Phase 10E — deterministic chemistry helpers (elements + reactions).

Every ``output`` id must exist in ``realm.materials.MATERIALS``.
"""

from __future__ import annotations

from typing import Final

# Element symbols for UI / future periodic table views (49-slot compatible).
ELEMENT_SYMBOLS: Final[tuple[str, ...]] = (
    "H",
    "He",
    "Li",
    "Be",
    "B",
    "C",
    "N",
    "O",
    "F",
    "Ne",
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "S",
    "Cl",
    "Ar",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Ge",
    "As",
    "Se",
    "Br",
    "Kr",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
)

_REACTIONS: Final[list[tuple[tuple[str, str], tuple[str, int]]]] = [
    (("sand", "coal"), ("glass", 1)),
    (("iron_ore", "coal"), ("iron_ingot", 1)),
    (("copper_ore", "coal"), ("copper_ingot", 1)),
    (("clay", "coal"), ("brick", 2)),
    (("grain", "coal"), ("bread", 1)),
    (("timber", "coal"), ("charcoal", 2)),
    (("stone", "coal"), ("quicklime", 1)),
    (("limestone", "coal"), ("quicklime", 2)),
    (("wild_herb", "coal"), ("medicine", 1)),
    (("fish", "coal"), ("smoked_fish", 1)),
    (("raw_silica", "coal"), ("fused_silica", 1)),
    (("iron_ore", "copper_ore"), ("slag", 1)),
    (("iron_ingot", "coal"), ("steel_ingot", 1)),
    (("copper_ingot", "coal"), ("copper_wire", 1)),
    (("tin_ore", "coal"), ("tin_ingot", 1)),
    (("lead_ore", "coal"), ("lead_ingot", 1)),
    (("phosphate_ore", "coal"), ("phosphate_meal", 1)),
    (("saltpeter_ore", "sulfur_ore"), ("gunpowder", 1)),
    (("sulfur_ore", "coal"), ("sulfur_ore_refined", 1)),
    (("saltpeter_ore", "coal"), ("refined_saltpeter", 1)),
    (("iron_ingot", "tin_ore"), ("bronze_ingot", 1)),
    (("flour", "coal"), ("bread", 2)),
    (("clay", "sand"), ("mortar", 1)),
    (("pig_iron", "coal"), ("cast_iron", 1)),
    (("oil_shale", "coal"), ("shale_oil", 1)),
    (("platinum_ore", "coal"), ("refined_platinum", 1)),
    (("copper_ore", "tin_ore"), ("bronze_ingot", 1)),
    (("iron_ingot", "copper_ingot"), ("bronze_ingot", 1)),
    (("limestone", "clay"), ("mortar", 2)),
    (("rope", "coal"), ("charcoal", 1)),
    (("lumber", "coal"), ("charcoal", 1)),
    (("clay", "limestone"), ("brick", 1)),
    (("sand", "limestone"), ("glass", 1)),
    (("iron_ore", "limestone"), ("slag", 2)),
    (("grain", "clay"), ("pottery", 1)),
    (("rare_earth_ore", "coal"), ("slag", 1)),
    (("sulfur_ore_refined", "saltpeter_ore"), ("gunpowder", 1)),
    (("sulfuric_acid", "copper_ingot"), ("copper_wire", 1)),
    (("cast_iron", "coal"), ("steel_ingot", 1)),
    (("tin_ingot", "copper_ingot"), ("bronze_ingot", 1)),
    (("lead_ingot", "coal"), ("slag", 1)),
    (("phosphate_meal", "clay"), ("mortar", 1)),
    (("fused_silica", "sand"), ("glass", 1)),
]

REACTIONS_PUBLIC: Final[list[dict[str, object]]] = [
    {"inputs": list(pair[0]), "output": pair[1][0], "qty": pair[1][1]} for pair in _REACTIONS
]


def try_reaction(a: str, b: str) -> tuple[str, int] | None:
    """Return ``(output_material_id, qty)`` if a known reaction exists (unordered)."""
    x, y = sorted((a.casefold(), b.casefold()))
    for (left, right), out in _REACTIONS:
        l, r = sorted((left.casefold(), right.casefold()))
        if (l, r) == (x, y):
            return (out[0], int(out[1]))
    return None

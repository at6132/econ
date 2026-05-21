"""
Material quality tiers.

Quality is tracked as a tag on inventory slots. In the ledger, inventory is
stored in quality-keyed buckets: (party, material, quality) → qty.
Standard quality is the default — all existing code still works.
"""

from __future__ import annotations

from typing import Final

QUALITY_LOW: Final[str] = "low"
QUALITY_STANDARD: Final[str] = "standard"
QUALITY_HIGH: Final[str] = "high"

QUALITY_TIERS: Final[tuple[str, ...]] = (QUALITY_LOW, QUALITY_STANDARD, QUALITY_HIGH)

# Grade thresholds for extraction quality
GRADE_HIGH_THRESHOLD: Final[float] = 0.60
GRADE_LOW_THRESHOLD: Final[float] = 0.30

# Price multipliers per quality tier
QUALITY_PRICE_MULT: dict[str, float] = {
    QUALITY_LOW: 0.80,
    QUALITY_STANDARD: 1.00,
    QUALITY_HIGH: 1.25,
}

# Recipe yield multiplier when using this input quality
QUALITY_YIELD_MULT: dict[str, float] = {
    QUALITY_LOW: 0.85,
    QUALITY_STANDARD: 1.00,
    QUALITY_HIGH: 1.10,
}

# Materials that support quality tiers (raw extracted ores + smelted metals)
QUALITY_ELIGIBLE_MATERIALS: frozenset[str] = frozenset({
    "iron_ore",
    "coal",
    "copper_ore",
    "tin_ore",
    "lead_ore",
    "sulfur_ore",
    "phosphate_ore",
    "saltpeter_ore",
    "rare_earth_ore",
    "platinum_ore",
    "clay",
    "stone",
    "sand",
    "timber",
    "iron_ingot",
    "steel_ingot",
    "copper_ingot",
    "tin_ingot",
    "lead_ingot",
    "pig_iron",
    "cast_iron",
    "bronze_ingot",
})

# Subsurface field names for grade → output quality on extraction
MATERIAL_GRADE_FIELD: dict[str, str] = {
    "iron_ore": "iron_ore_grade",
    "coal": "coal_grade",
    "copper_ore": "copper_ore_grade",
    "tin_ore": "tin_grade",
    "lead_ore": "lead_grade",
    "sulfur_ore": "sulfur_grade",
    "phosphate_ore": "phosphate_grade",
    "clay": "clay_grade",
    "stone": "silica_grade",
    "sand": "silica_grade",
    "timber": "clay_grade",
}


def grade_to_quality(grade: float) -> str:
    if grade >= GRADE_HIGH_THRESHOLD:
        return QUALITY_HIGH
    if grade >= GRADE_LOW_THRESHOLD:
        return QUALITY_STANDARD
    return QUALITY_LOW


def quality_price_multiplier(quality: str) -> float:
    return QUALITY_PRICE_MULT.get(quality, 1.0)


def quality_yield_multiplier(quality: str) -> float:
    return QUALITY_YIELD_MULT.get(quality, 1.0)

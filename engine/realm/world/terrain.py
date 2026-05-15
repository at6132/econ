"""Terrain types for plots (Primitive 1)."""

from __future__ import annotations

from enum import Enum


class Terrain(str, Enum):
    PLAINS = "plains"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    DESERT = "desert"
    TUNDRA = "tundra"
    SWAMP = "swamp"
    # Phase 10 — added by the continental layout. Hills are an upland biome
    # between plains and mountain (drier, lower-grade ore than mountain).
    # Existing terrain-conditional code paths treat HILLS like PLAINS unless
    # they explicitly opt in, so adding this enum value is backwards-compat.
    HILLS = "hills"
    WATER_SHALLOW = "water_shallow"
    WATER_DEEP = "water_deep"

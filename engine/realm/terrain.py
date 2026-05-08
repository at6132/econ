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
    WATER_SHALLOW = "water_shallow"
    WATER_DEEP = "water_deep"

"""Lab preset schema — data-driven sandbox definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

LabBase = Literal["frontier", "genesis"]
LabCategory = Literal[
    "Strategy",
    "Markets",
    "Social",
    "Production",
    "Stress",
    "Tutorial",
]

LAB_CATEGORIES: tuple[LabCategory, ...] = (
    "Strategy",
    "Markets",
    "Social",
    "Production",
    "Stress",
    "Tutorial",
)


class LabOverrideSchema(TypedDict, total=False):
    seed: dict[str, Any]
    map_scale_pct: dict[str, Any]
    cash_scale_pct: dict[str, Any]
    settler_count: dict[str, Any]
    sim_speed: dict[str, Any]


class LabOverrides(TypedDict, total=False):
    seed: int
    map_scale_pct: int
    cash_scale_pct: int
    settler_count: int
    sim_speed: int


@dataclass(frozen=True, slots=True)
class LabPreset:
    id: str
    title: str
    description: str
    category: LabCategory
    tags: tuple[str, ...]
    base: LabBase
    params: dict[str, Any]
    overlays: dict[str, bool] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)
    featured: bool = False

    def public_dict(self) -> dict[str, Any]:
        gw = self.params.get("grid_width")
        gh = self.params.get("grid_height")
        grid_label = f"{gw}×{gh}" if gw and gh else "—"
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "base": self.base,
            "grid_label": grid_label,
            "featured": self.featured,
            "default_seed": int(self.defaults.get("seed", 42)),
            "default_sim_speed": int(self.defaults.get("sim_speed", 2)),
        }

    def override_schema(self) -> LabOverrideSchema:
        schema: LabOverrideSchema = {
            "seed": {"type": "int", "min": 1, "max": 999_999, "default": 42},
            "map_scale_pct": {
                "type": "int",
                "min": 50,
                "max": 150,
                "default": 100,
                "step": 10,
            },
            "cash_scale_pct": {
                "type": "int",
                "min": 25,
                "max": 400,
                "default": 100,
                "step": 25,
            },
            "sim_speed": {
                "type": "int",
                "min": 0,
                "max": 2,
                "default": int(self.defaults.get("sim_speed", 2)),
            },
        }
        if self.base == "genesis":
            lo = int(self.params.get("settler_count", 5))
            schema["settler_count"] = {
                "type": "int",
                "min": 0,
                "max": max(lo * 3, 80),
                "default": lo,
            }
        return schema

    def detail_dict(self) -> dict[str, Any]:
        out = self.public_dict()
        out["params"] = dict(self.params)
        out["overlays"] = dict(self.overlays)
        out["override_schema"] = self.override_schema()
        return out

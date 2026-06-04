"""Static technology tree — eras and research nodes."""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

TechEraId = Literal[
    "industrial",
    "electrical",
    "chemical",
    "digital",
    "advanced_mats",
    "post_scarcity",
]

TechNodeId = Literal[
    "precision_tooling",
    "workshop_engineering",
    "electric_motors",
    "telegraph",
    "steam_turbine",
    "synthetic_dyes",
    "explosives",
    "fertilizers",
    "vacuum_tubes",
    "transistors",
    "computers",
    "carbon_fiber",
    "nano_materials",
    "fusion_power",
    "molecular_assembly",
]


class EraSpec(TypedDict):
    era_id: TechEraId
    prereq: TechEraId | None
    unlocked_at_boot: bool


class TechNodeSpec(TypedDict, total=False):
    era: TechEraId
    prereq_nodes: list[str]
    research_cost_days: int
    unlocks_recipes: list[str]
    efficiency_bonus: dict[str, float]
    unlocks_capabilities: list[str]


ERAS: Final[dict[str, EraSpec]] = {
    "industrial": {
        "era_id": "industrial",
        "prereq": None,
        "unlocked_at_boot": True,
    },
    "electrical": {
        "era_id": "electrical",
        "prereq": "industrial",
        "unlocked_at_boot": False,
    },
    "chemical": {
        "era_id": "chemical",
        "prereq": "electrical",
        "unlocked_at_boot": False,
    },
    "digital": {
        "era_id": "digital",
        "prereq": "chemical",
        "unlocked_at_boot": False,
    },
    "advanced_mats": {
        "era_id": "advanced_mats",
        "prereq": "digital",
        "unlocked_at_boot": False,
    },
    "post_scarcity": {
        "era_id": "post_scarcity",
        "prereq": "advanced_mats",
        "unlocked_at_boot": False,
    },
}

TECH_NODES: Final[dict[str, TechNodeSpec]] = {
    "precision_tooling": {
        "era": "industrial",
        "prereq_nodes": [],
        "research_cost_days": 15,
        "unlocks_recipes": [],
        "efficiency_bonus": {},
        "unlocks_capabilities": ["custom_recipe"],
    },
    "workshop_engineering": {
        "era": "industrial",
        "prereq_nodes": ["precision_tooling"],
        "research_cost_days": 25,
        "unlocks_recipes": [],
        "efficiency_bonus": {},
        "unlocks_capabilities": ["custom_blueprint"],
    },
    "electric_motors": {
        "era": "electrical",
        "prereq_nodes": [],
        "research_cost_days": 30,
        "unlocks_recipes": ["electric_pump", "electric_drill"],
        "efficiency_bonus": {},
        "unlocks_capabilities": ["workshop_focus"],
    },
    "telegraph": {
        "era": "electrical",
        "prereq_nodes": ["electric_motors"],
        "research_cost_days": 20,
        "unlocks_recipes": ["telegraph_line"],
        "efficiency_bonus": {"mine_coal": 0.1},
    },
    "steam_turbine": {
        "era": "electrical",
        "prereq_nodes": ["electric_motors"],
        "research_cost_days": 45,
        "unlocks_recipes": ["turbine_generator"],
        "efficiency_bonus": {"coal_generator": 0.25},
    },
    "synthetic_dyes": {
        "era": "chemical",
        "prereq_nodes": ["steam_turbine"],
        "research_cost_days": 40,
        "unlocks_recipes": ["dye_synthesis"],
        "efficiency_bonus": {},
    },
    "explosives": {
        "era": "chemical",
        "prereq_nodes": ["synthetic_dyes"],
        "research_cost_days": 35,
        "unlocks_recipes": ["blast_mining"],
        "efficiency_bonus": {"mine_iron_ore": 0.3, "mine_coal": 0.3},
    },
    "fertilizers": {
        "era": "chemical",
        "prereq_nodes": ["synthetic_dyes"],
        "research_cost_days": 50,
        "unlocks_recipes": ["fertilizer_plant"],
        "efficiency_bonus": {"grow_grain": 0.4},
    },
    "vacuum_tubes": {
        "era": "digital",
        "prereq_nodes": ["explosives"],
        "research_cost_days": 60,
        "unlocks_recipes": ["radio_broadcast"],
        "efficiency_bonus": {},
    },
    "transistors": {
        "era": "digital",
        "prereq_nodes": ["vacuum_tubes"],
        "research_cost_days": 80,
        "unlocks_recipes": ["semiconductor_fab"],
        "efficiency_bonus": {"telegraph_line": 0.5},
    },
    "computers": {
        "era": "digital",
        "prereq_nodes": ["transistors"],
        "research_cost_days": 100,
        "unlocks_recipes": ["automated_factory"],
        "efficiency_bonus": {"all": 0.1},
        "unlocks_capabilities": ["advanced_blueprint", "public_custom_recipes"],
    },
    "carbon_fiber": {
        "era": "advanced_mats",
        "prereq_nodes": ["computers"],
        "research_cost_days": 90,
        "unlocks_recipes": ["composite_build"],
        "efficiency_bonus": {},
    },
    "nano_materials": {
        "era": "advanced_mats",
        "prereq_nodes": ["carbon_fiber"],
        "research_cost_days": 150,
        "unlocks_recipes": ["nano_fabrication"],
        "efficiency_bonus": {"all": 0.2},
    },
    "fusion_power": {
        "era": "post_scarcity",
        "prereq_nodes": ["nano_materials"],
        "research_cost_days": 300,
        "unlocks_recipes": ["fusion_reactor"],
        "efficiency_bonus": {"all": 0.5},
    },
    "molecular_assembly": {
        "era": "post_scarcity",
        "prereq_nodes": ["fusion_power"],
        "research_cost_days": 500,
        "unlocks_recipes": ["assembler"],
        "efficiency_bonus": {"all": 1.0},
        "unlocks_capabilities": ["blueprint_public_license"],
    },
}


def era_node_ids(era_id: str) -> list[str]:
    """All tech node ids belonging to ``era_id``."""
    return [nid for nid, spec in TECH_NODES.items() if spec["era"] == era_id]


def era_spec(era_id: str) -> EraSpec | None:
    return ERAS.get(era_id)  # type: ignore[return-value]


def node_spec(node_id: str) -> TechNodeSpec | None:
    return TECH_NODES.get(node_id)  # type: ignore[return-value]

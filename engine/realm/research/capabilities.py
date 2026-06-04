"""Player capabilities unlocked by research (gates custom build / open-ended play)."""

from __future__ import annotations

from typing import Any, Final

from realm.core.ids import PartyId
from realm.world import World

# capability_id → spec (boot = granted at world start for every party)
CAPABILITY_SPECS: Final[dict[str, dict[str, Any]]] = {
    "custom_material": {
        "label": "Register custom materials",
        "description": "Define new matter types others can trade and use in recipes.",
        "boot": True,
    },
    "custom_recipe": {
        "label": "Author custom recipes",
        "description": "Combine catalog and custom materials into new production lines.",
        "boot": False,
    },
    "custom_blueprint": {
        "label": "Design custom facilities",
        "description": "Register blueprints up to 5×5 cells with chosen recipes.",
        "boot": False,
        "max_footprint_cells": 25,
    },
    "advanced_blueprint": {
        "label": "Large custom facilities",
        "description": "Register blueprints up to 8×8 cells.",
        "boot": False,
        "max_footprint_cells": 64,
    },
    "blueprint_public_license": {
        "label": "Public blueprint licensing",
        "description": "Publish facility designs and charge license fees.",
        "boot": False,
    },
    "workshop_focus": {
        "label": "Workshop production focus",
        "description": "Specialize a plot: boost one recipe, trade off others on site.",
        "boot": False,
    },
    "public_custom_recipes": {
        "label": "Publish custom recipes",
        "description": "Share authored recipes with other parties.",
        "boot": False,
    },
}

_BOOT_CAPABILITIES: Final[frozenset[str]] = frozenset(
    cid for cid, spec in CAPABILITY_SPECS.items() if spec.get("boot")
)


def _cap_store(world: World) -> dict[str, list[str]]:
    raw = world.scenario_state.setdefault("research_capabilities", {})
    if not isinstance(raw, dict):
        world.scenario_state["research_capabilities"] = {}
        raw = world.scenario_state["research_capabilities"]
    return raw  # type: ignore[return-value]


def party_capability_ids(world: World, party: PartyId) -> set[str]:
    out = set(_BOOT_CAPABILITIES)
    raw = _cap_store(world).get(str(party), [])
    if isinstance(raw, list):
        out.update(str(x) for x in raw)
    return out


def grant_capabilities(world: World, party: PartyId, capability_ids: list[str]) -> list[str]:
    """Grant new capabilities; returns ids that were newly added."""
    store = _cap_store(world)
    current = party_capability_ids(world, party)
    newly: list[str] = []
    for cid in capability_ids:
        if cid not in CAPABILITY_SPECS:
            continue
        if cid in current:
            continue
        current.add(cid)
        newly.append(cid)
    if newly:
        store[str(party)] = sorted(current - _BOOT_CAPABILITIES)
    return newly


def party_has_capability(world: World, party: PartyId, capability_id: str) -> bool:
    return capability_id in party_capability_ids(world, party)


def party_max_blueprint_cells(world: World, party: PartyId) -> int:
    """0 means custom blueprints are not allowed."""
    caps = party_capability_ids(world, party)
    best = 0
    if "advanced_blueprint" in caps:
        best = max(best, int(CAPABILITY_SPECS["advanced_blueprint"]["max_footprint_cells"]))
    if "custom_blueprint" in caps:
        best = max(
            best, int(CAPABILITY_SPECS["custom_blueprint"]["max_footprint_cells"])
        )
    return best


def capabilities_public(world: World, party: PartyId) -> list[dict[str, Any]]:
    """UI/API list of capabilities with lock state."""
    have = party_capability_ids(world, party)
    out: list[dict[str, Any]] = []
    for cid, spec in CAPABILITY_SPECS.items():
        out.append(
            {
                "id": cid,
                "label": str(spec["label"]),
                "description": str(spec.get("description", "")),
                "unlocked": cid in have,
                "boot": bool(spec.get("boot")),
            }
        )
    return out

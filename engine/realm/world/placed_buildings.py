"""Placed building instances on plot grids."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from realm.core.ids import PartyId, PlotId
from realm.production.decay import BUILDING_CONDITION_FULL_BPS
from realm.world import World


@dataclass
class PlacedBuilding:
    instance_id: str
    blueprint_id: str
    plot_id: str
    grid_x: int
    grid_y: int
    built_at_tick: int
    built_by: str
    status: str
    efficiency_pct: int
    missed_maintenance_cycles: int
    due_at_tick: int
    sub_plot_id: str | None = None


def legacy_plot_building_row(world: World, pb: PlacedBuilding) -> dict[str, Any]:
    """Dict shape expected by production, decay, energy, and genesis code."""
    bp = world.blueprints.get(pb.blueprint_id)
    label = bp.name if bp is not None else pb.blueprint_id
    return {
        "instance_id": pb.instance_id,
        "condition_bps": BUILDING_CONDITION_FULL_BPS,
        "plot_id": pb.plot_id,
        "party": pb.built_by,
        "building_id": pb.blueprint_id,
        "blueprint_id": pb.blueprint_id,
        "label": label,
        "cost_cents": 0,
        "build_mode": "blueprint",
        "completes_at_tick": int(pb.built_at_tick),
        "grid_x": int(pb.grid_x),
        "grid_y": int(pb.grid_y),
        "status": pb.status,
        "sub_plot_id": pb.sub_plot_id,
    }


def sync_plot_buildings_from_placed(world: World) -> None:
    """Rebuild ``plot_buildings`` list from ``placed_buildings`` (legacy readers)."""
    rows: list[dict[str, Any]] = []
    for iid in sorted(world.placed_buildings.keys()):
        pb = world.placed_buildings[iid]
        rows.append(legacy_plot_building_row(world, pb))
    world.plot_buildings = rows


def register_placed_building(world: World, pb: PlacedBuilding) -> None:
    world.placed_buildings[pb.instance_id] = pb
    world.plot_placed_buildings.setdefault(pb.plot_id, []).append(pb.instance_id)
    world.plot_buildings.append(legacy_plot_building_row(world, pb))

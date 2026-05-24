"""Bootstrap a lab world from a preset id + optional runtime overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

from realm.labs.preset_registry import get_lab_preset
from realm.labs.preset_schema import LabOverrides, LabPreset
from realm.world.world import bootstrap_frontier, bootstrap_genesis

if TYPE_CHECKING:
    from realm.world import World


def _apply_scale(value: int, scale_pct: int) -> int:
    return max(1, int(value * scale_pct / 100))


def _merged_params(preset: LabPreset, overrides: LabOverrides | None) -> dict:
    params = dict(preset.params)
    ov = overrides or {}
    scale_pct = int(ov.get("map_scale_pct", 100))
    if scale_pct != 100:
        if "grid_width" in params:
            params["grid_width"] = _apply_scale(int(params["grid_width"]), scale_pct)
        if "grid_height" in params:
            params["grid_height"] = _apply_scale(int(params["grid_height"]), scale_pct)
    cash_scale = int(ov.get("cash_scale_pct", 100))
    if cash_scale != 100:
        for key in ("starting_cash_cents", "player_starting_cash_cents"):
            if key in params:
                params[key] = _apply_scale(int(params[key]), cash_scale)
    if "settler_count" in ov and preset.base == "genesis":
        params["settler_count"] = int(ov["settler_count"])
    return params


def bootstrap_lab_preset(
    *,
    preset_id: str,
    seed: int | None = None,
    overrides: LabOverrides | None = None,
    world_name: str = "",
) -> World:
    preset = get_lab_preset(preset_id)
    params = _merged_params(preset, overrides)
    run_seed = int(seed if seed is not None else preset.defaults.get("seed", 42))

    if preset.base == "frontier":
        scenario_id = str(params.pop("scenario_id", "frontier"))
        world = bootstrap_frontier(
            seed=run_seed,
            grid_width=int(params.get("grid_width", 24)),
            grid_height=int(params.get("grid_height", 18)),
            starting_cash_cents=int(
                params.get("starting_cash_cents", 10_000_000)
            ),
            scenario_id=scenario_id,
            uniform_plots=bool(params.get("uniform_plots", False)),
        )
    else:
        world = bootstrap_genesis(
            seed=run_seed,
            grid_width=int(params.get("grid_width", 32)),
            grid_height=int(params.get("grid_height", 24)),
            settler_count=params.get("settler_count"),
            settler_spawn_cap=params.get("settler_spawn_cap"),
            player_starting_cash_cents=int(
                params.get(
                    "player_starting_cash_cents",
                    params.get("starting_cash_cents", 10_000_000),
                )
            ),
            map_layout=str(params.get("map_layout", "auto")),
        )

    if world_name.strip():
        world.world_name = world_name.strip()

    world.scenario_state["lab_mode"] = True
    world.scenario_state["lab_preset_id"] = preset.id
    world.scenario_state["lab_category"] = preset.category
    world.scenario_state["lab_display_id"] = f"lab:{preset.id}"
    world.scenario_state["lab_title"] = preset.title
    world.scenario_state["lab_seed"] = run_seed
    if overrides:
        world.scenario_state["lab_overrides"] = dict(overrides)

    return world

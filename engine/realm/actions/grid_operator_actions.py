"""Grid utility operator franchise actions."""

from __future__ import annotations

from typing import Any

from realm.core.ids import PartyId, PlotId
from realm.world import World


def register_grid_operator(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    rate_cents_per_kwh: int,
    min_wh_per_day: int = 0,
    max_wh_per_day: int | None = None,
) -> dict[str, Any]:
    from realm.infrastructure.grid_operators import register_grid_operator as _register

    return _register(
        world,
        party,
        plot_id,
        rate_cents_per_kwh=rate_cents_per_kwh,
        min_wh_per_day=min_wh_per_day,
        max_wh_per_day=max_wh_per_day,
    )


def update_grid_operator_tariff(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    rate_cents_per_kwh: int | None = None,
    min_wh_per_day: int | None = None,
    max_wh_per_day: int | None = None,
) -> dict[str, Any]:
    from realm.infrastructure.grid_operators import update_grid_operator_tariff as _update

    return _update(
        world,
        party,
        plot_id,
        rate_cents_per_kwh=rate_cents_per_kwh,
        min_wh_per_day=min_wh_per_day,
        max_wh_per_day=max_wh_per_day,
    )


def unregister_grid_operator(
    world: World, party: PartyId, plot_id: PlotId
) -> dict[str, Any]:
    from realm.infrastructure.grid_operators import unregister_grid_operator as _unregister

    return _unregister(world, party, plot_id)

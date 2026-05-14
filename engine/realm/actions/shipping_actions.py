"""Shipping & route operator actions.

Functions:
  * ``register_route``    — register the player as operator of a region-pair route
  * ``revise_route_fee``  — adjust the per-tile toll on a route the player operates
"""

from __future__ import annotations

from typing import Any

from realm.core.ids import PartyId, PlotId
from realm.world import World


def register_route(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    from_region: str,
    to_region: str,
    fee_per_tile_cents: int,
) -> dict[str, Any]:
    """Register ``party`` as the operator of a region-to-region shipping route.

    Proxy to :func:`realm.infrastructure.route_operators.register_route`. See
    that function's docstring for the full precondition list.
    """
    from realm.infrastructure.route_operators import register_route as _register

    return _register(world, party, plot_id, from_region, to_region, fee_per_tile_cents)


def revise_route_fee(
    world: World,
    party: PartyId,
    route_key: str,
    new_fee_per_tile_cents: int,
) -> dict[str, Any]:
    """Update the per-tile fee on a route the ``party`` already operates."""
    from realm.infrastructure.route_operators import set_operator_fee

    return set_operator_fee(world, party, route_key, new_fee_per_tile_cents)

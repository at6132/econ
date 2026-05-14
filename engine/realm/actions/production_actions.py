"""Production proxies — thin player-facing wrappers around the production tick.

Functions:
  * ``start_production_on_plot`` — proxy to ``realm.production.start_production``
  * ``harvest_plot_output_stock`` — harvest-then-add, returning ActionResult
"""

from __future__ import annotations

from typing import Any

from realm.actions._shared import ActionErr, ActionOk, ActionResult
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.infrastructure.plot_logistics import harvest_plot_output_to_party
from realm.production import start_production
from realm.world import World


def harvest_plot_output_stock(
    world: World, party: PartyId, plot_id: PlotId, material: str, qty: int
) -> ActionResult:
    r = harvest_plot_output_to_party(world, party, plot_id, MaterialId(material), qty)
    if r.get("ok"):
        return ActionOk(ok=True)
    return ActionErr(ok=False, reason=str(r.get("reason", "error")))


def start_production_on_plot(
    world: World, party: PartyId, plot_id: PlotId, recipe_id: str
) -> dict[str, Any]:
    """Proxy to ``production.start_production`` (full result dict for API / agents)."""
    return start_production(world, party, plot_id, recipe_id)

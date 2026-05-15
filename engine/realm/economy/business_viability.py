"""Phase 10C — daily business footprint checks + production observation hooks."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.economy.businesses import BusinessEntity
from realm.world import World


def record_business_production_for_completed_run(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    recipe_id: str,
    eff_out: dict[MaterialId, int],
) -> None:
    """Rolling 7-game-day output totals per business (for viability / UI)."""
    if not eff_out:
        return
    day = int(world.tick) // 1440
    by_biz = world.scenario_state.setdefault("business_production_by_day", {})
    for biz in world.businesses.values():
        if not isinstance(biz, BusinessEntity):
            continue
        if biz.owner_party != party:
            continue
        if str(plot_id) not in {str(p) for p in biz.registered_plot_ids}:
            continue
        bucket = by_biz.setdefault(str(biz.business_id), {})
        day_row = bucket.setdefault(str(day), {"units": 0, "recipe_ids": set()})
        day_row["units"] = int(day_row["units"]) + int(sum(int(q) for q in eff_out.values()))
        ids = day_row["recipe_ids"]
        if isinstance(ids, set):
            ids.add(str(recipe_id))


def tick_business_viability(world: World) -> None:
    """Once per game-day: suspend businesses that lost their declared plot footprint."""
    if int(world.tick) <= 0 or int(world.tick) % 1440 != 0:
        return
    for bid, biz in list(world.businesses.items()):
        if not isinstance(biz, BusinessEntity):
            continue
        if biz.status != "active":
            continue
        owner = PartyId(str(biz.owner_party))
        lost = False
        for pid in biz.registered_plot_ids:
            plot = world.plots.get(PlotId(str(pid)))
            if plot is None or plot.owner != owner:
                lost = True
                break
        if not lost:
            continue
        world.businesses[bid] = BusinessEntity(
            business_id=biz.business_id,
            owner_party=biz.owner_party,
            business_name=biz.business_name,
            business_type_tag=biz.business_type_tag,
            description=biz.description,
            registered_at_tick=biz.registered_at_tick,
            registered_plot_ids=biz.registered_plot_ids,
            sub_account_label=biz.sub_account_label,
            status="suspended",
            suspension_reason="lost registered plot footprint",
            public_profile=biz.public_profile,
            last_viability_check_tick=int(world.tick),
        )

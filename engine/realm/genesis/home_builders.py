"""Phase 9G — Home builder archetype (residential developer).

One NPC per starting town builds residences over time, growing housing
capacity so the homeless laborer pool gets absorbed. Players in later
phases compete in the same residential market. The builder is dormant
between build cycles (no idle CPU cost) and never undercuts player
businesses -- they only place residences on plots they already own.

Each builder is seeded with:
  - 1 land plot adjacent to its town (claimed at bootstrap).
  - $500,000 starting cash (enough for ~3 turnkey residences).
  - 50× lumber + 50× brick + 25× timber so the first build can fire
    without needing to source materials.

``tick_home_builders`` runs every ``HOME_BUILDER_CYCLE_TICKS`` (default
14 game-days). On each cycle, every builder that has spare cash + space
on its plot kicks off one residence build via the standard turnkey
build_on_plot path -- so the residence flows through the same
plot_buildings + maintenance schedule as any player-built home.
"""

from __future__ import annotations

from typing import Final

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.world import World


HOME_BUILDER_PARTY_ID_PREFIX: Final[str] = "frontier_homes_co_"
HOME_BUILDER_STARTING_CASH_CENTS: Final[int] = 500_000  # $5,000
HOME_BUILDER_CYCLE_TICKS: Final[int] = 14 * 1_440  # 14 game-days
HOME_BUILDER_STARTING_MATERIALS: Final[dict[MaterialId, int]] = {
    MaterialId("lumber"): 50,
    MaterialId("brick"): 50,
    MaterialId("timber"): 25,
    MaterialId("stone"): 20,
}


def home_builder_party_id_for_island(island_id: int) -> PartyId:
    return PartyId(f"{HOME_BUILDER_PARTY_ID_PREFIX}{island_id}")


def _pick_builder_plot(world: World, island_id: int, town_plots: set[str]) -> PlotId | None:
    """Find an unclaimed land plot on the island adjacent to (or near)
    the existing town residences. Falls back to any unclaimed land plot
    on the island if nothing nearby is free.
    """
    plot_islands = world.scenario_state.get("plot_islands") or {}
    candidates: list[tuple[int, str]] = []
    fallback: list[str] = []
    for pid_s, isl in plot_islands.items():
        if int(isl) != int(island_id):
            continue
        plot = world.plots.get(PlotId(pid_s))
        if plot is None or plot.owner is not None:
            continue
        fallback.append(pid_s)
        # Score = chebyshev distance to nearest town plot. Lower = better.
        score = min(
            (max(abs(int(plot.x) - int(world.plots[PlotId(tp)].x)),
                 abs(int(plot.y) - int(world.plots[PlotId(tp)].y)))
             for tp in town_plots if PlotId(tp) in world.plots),
            default=999,
        )
        candidates.append((score, pid_s))
    if candidates:
        candidates.sort()
        return PlotId(candidates[0][1])
    if fallback:
        return PlotId(sorted(fallback)[0])
    return None


def seed_home_builders(world: World) -> list[PartyId]:
    """Spawn one home_builder NPC per starting town.

    Idempotent: re-running on a world that already has the builders is
    a no-op.
    """
    starting_towns = world.scenario_state.get("starting_towns_by_island") or {}
    if not starting_towns:
        return []
    created: list[PartyId] = []
    for isl_s, town_id in starting_towns.items():
        island_id = int(isl_s)
        builder = home_builder_party_id_for_island(island_id)
        if builder in world.parties:
            continue
        town = world.towns.get(town_id)
        if town is None:
            continue
        world.parties.add(builder)
        world.reputation.setdefault(str(builder), {"honored": 0, "breached": 0})
        world.party_display_names[str(builder)] = f"Frontier Homes Co. (Island {island_id})"
        acct = party_cash_account(builder)
        world.ledger.ensure_account(acct)
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=HOME_BUILDER_STARTING_CASH_CENTS,
        )
        if isinstance(tr, MoneyErr):
            world.parties.discard(builder)
            continue
        # Seed materials so the first build cycle doesn't stall.
        for mid, qty in HOME_BUILDER_STARTING_MATERIALS.items():
            ad = world.inventory.add(builder, mid, qty)
            if isinstance(ad, MatterErr):
                pass
        # Claim a plot for the builder near the town.
        town_plot_strs = {str(p) for p in town.residential_plots}
        plot_id = _pick_builder_plot(world, island_id, town_plot_strs)
        if plot_id is not None:
            world.plots[plot_id].owner = builder
            world.scenario_state.setdefault("home_builder_plots", {})[
                str(builder)
            ] = str(plot_id)
        created.append(builder)
        log_event(
            world,
            "home_builder_seeded",
            f"Home builder {builder} placed on island {island_id} "
            f"with ${HOME_BUILDER_STARTING_CASH_CENTS // 100} cash + materials",
            party=str(builder),
            island_id=int(island_id),
            plot_id=str(plot_id) if plot_id else None,
        )
    return created


def tick_home_builders(world: World) -> int:
    """Phase 9G — once per cycle, every home builder kicks off one
    residence build on their owned plot (if they have materials).

    Returns the number of residences started this cycle.
    """
    from realm.production.buildings import build_on_plot

    if int(world.tick) % HOME_BUILDER_CYCLE_TICKS != 0:
        return 0
    plots_map = world.scenario_state.get("home_builder_plots") or {}
    if not plots_map:
        return 0
    started = 0
    for builder_s, plot_s in plots_map.items():
        builder = PartyId(builder_s)
        plot_id = PlotId(plot_s)
        plot = world.plots.get(plot_id)
        if plot is None or plot.owner != builder:
            continue
        # If their plot already has a completed or in-flight residence, pick
        # another adjacent unclaimed plot to keep growing the town.
        has_residence = any(
            b.get("plot_id") == str(plot_id)
            and b.get("building_id") == "residence"
            for b in world.plot_buildings
        )
        if has_residence:
            town = next(
                (t for t in world.towns.values() if t.island_id == int(_island_for_plot(world, plot_id) or 0)),
                None,
            )
            town_plot_strs = {str(p) for p in (town.residential_plots if town else [])}
            new_plot = _pick_builder_plot(
                world, int(_island_for_plot(world, plot_id) or 0), town_plot_strs
            )
            if new_plot is None:
                continue
            plot = world.plots[new_plot]
            plot.owner = builder
            world.scenario_state["home_builder_plots"][builder_s] = str(new_plot)
            plot_id = new_plot
        res = build_on_plot(world, builder, plot_id, "residence", build_mode="self_build")
        if res.get("ok"):
            started += 1
            log_event(
                world,
                "home_builder_started",
                f"{builder} started residence build on {plot_id}",
                party=str(builder),
                plot_id=str(plot_id),
                building_id="residence",
            )
    return started


def _island_for_plot(world: World, plot_id: PlotId) -> int | None:
    plot_islands = world.scenario_state.get("plot_islands") or {}
    raw = plot_islands.get(str(plot_id))
    return int(raw) if raw is not None else None

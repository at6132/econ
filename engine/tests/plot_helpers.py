"""Find claimable land plots in seeded worlds (tests only)."""

from __future__ import annotations

from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world import World, claim_cost_cents_for_plot
from realm.world.terrain import Terrain


def ensure_party_can_claim(world: World, party: PartyId, plot_id: PlotId) -> None:
    """Top up player cash so density-scaled claim fees never block tests."""
    cost = int(claim_cost_cents_for_plot(world, plot_id))
    cash = party_cash_account(party)
    world.ledger.ensure_account(cash)
    need = cost + 50_000_00 - world.ledger.balance(cash)
    if need > 0:
        world.ledger.transfer(
            debit=system_reserve_account(),
            credit=cash,
            amount_cents=need,
        )


def first_land_plot_id(world: World, *, terrain_hint: str | None = None) -> PlotId:
    """Non-water plot with the lowest claim fee (prefers free frontier tiles)."""
    candidates: list[tuple[int, PlotId]] = []
    for pid, p in sorted(world.plots.items()):
        if p.owner is not None:
            continue
        if "water" in str(p.terrain).lower():
            continue
        if terrain_hint and terrain_hint.lower() not in str(p.terrain).lower():
            continue
        candidates.append((int(claim_cost_cents_for_plot(world, PlotId(pid))), PlotId(pid)))
    if not candidates:
        for pid, p in sorted(world.plots.items()):
            if p.owner is not None:
                continue
            if "water" in str(p.terrain).lower():
                p.terrain = Terrain.PLAINS
            candidates.append((int(claim_cost_cents_for_plot(world, PlotId(pid))), PlotId(pid)))
    if not candidates:
        raise RuntimeError("no plots in test world")
    candidates.sort(key=lambda x: (x[0], str(x[1])))
    return candidates[0][1]


def first_water_plot_id(world: World) -> PlotId:
    """Unclaimed water plot for terrain-gate tests."""
    for pid, p in sorted(world.plots.items()):
        if p.owner is not None:
            continue
        if "water" in str(p.terrain).lower():
            return PlotId(pid)
    raise RuntimeError("no unclaimed water plot in test world")


def first_terrain_plot_id(world: World, terrain: Terrain) -> PlotId:
    """Unclaimed plot with the requested terrain, if any."""
    for pid, p in sorted(world.plots.items()):
        if p.owner is None and p.terrain == terrain:
            return PlotId(pid)
    pid = first_land_plot_id(world)
    world.plots[pid].terrain = terrain
    return pid


def claimable_land_plot_id(
    world: World, party: PartyId, *, terrain_hint: str | None = None
) -> PlotId:
    """Land plot the party can afford to claim in tests."""
    pid = first_land_plot_id(world, terrain_hint=terrain_hint)
    ensure_party_can_claim(world, party, pid)
    return pid


def powered_land_plot_id(
    world: World,
    party: PartyId,
    *,
    terrain_hint: str | None = None,
) -> PlotId:
    """
    Like claimable_land_plot_id but also ensures the returned plot
    has grid power (places a power_shed if needed).
    Use for any test that calls start_production on an electric recipe.
    """
    from turnkey_fixtures import ensure_plot_grid_power

    pid = claimable_land_plot_id(world, party, terrain_hint=terrain_hint)
    ensure_plot_grid_power(world, pid)
    return pid


def two_adjacent_plot_ids(world: World) -> tuple[PlotId, PlotId]:
    """Two geometrically adjacent plots, coerced to land if needed."""
    for pid1, p1 in world.plots.items():
        for pid2, p2 in world.plots.items():
            if pid1 == pid2:
                continue
            if abs(p1.x - p2.x) + abs(p1.y - p2.y) != 1:
                continue
            if "water" in str(p1.terrain).lower():
                p1.terrain = Terrain.PLAINS
            if "water" in str(p2.terrain).lower():
                p2.terrain = Terrain.PLAINS
            return PlotId(pid1), PlotId(pid2)
    raise RuntimeError("no adjacent plots in test world")

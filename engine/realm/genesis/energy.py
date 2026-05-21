"""NPC energy companies — Tier-2 grid generators (Sprint 3 — Phase A.3).

Two named energy operators spawn near the map's geographic centre, each
with a pre-built ``power_shed`` and a starting cash buffer for coal. Their
buildings provide grid coverage immediately (warmup window of one game-hour
applies), so plots on the same road network as either operator can participate
in the regional electricity market (consumers still pay for electricity material).

Daily loop:

- Buy coal if their reserve is thin (≤ 5 days of operation).
- Fire a ``coal_generator`` batch if they have inputs and aren't already
  running one.
- List any produced electricity on the open market at the standard
  exchange ask — buyers anywhere can purchase and ship it out.

Energy companies intentionally do *not* register as route operators; their
job is to generate power, not to ship.
"""

from __future__ import annotations

from typing import Final

from realm.actions import start_production_on_plot
_POWER_STAGGER_TILES: int = 12
from realm.events.event_log import log_event
from realm.economy.pricing import exchange_ask_cents
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.economy.markets import market_buy, place_sell_order
from realm.production.recipe_sites import terrain_allows_workshop
from realm.world import World


NPC_ENERGY_IDS: Final[tuple[PartyId, ...]] = (
    PartyId("energy_central_north"),
    PartyId("energy_central_south"),
)
NPC_ENERGY_DISPLAY_NAMES: Final[dict[str, str]] = {
    "energy_central_north": "Polaris Power & Light",
    "energy_central_south": "Southern Watts Co.",
}
NPC_ENERGY_STARTING_CASH_CENTS: Final[int] = 250_000  # $2,500
NPC_ENERGY_TARGET_COAL_DAYS: Final[int] = 5
NPC_ENERGY_COAL_PER_DAY: Final[int] = 8

_TICKS_PER_GAME_DAY: Final[int] = 1440


def _bounds(world: World) -> tuple[int, int]:
    xs = [p.x for p in world.plots.values()]
    ys = [p.y for p in world.plots.values()]
    return (max(xs) + 1 if xs else 1, max(ys) + 1 if ys else 1)


def _pick_central_inland_plot(
    world: World, target_x: int, target_y: int, *, exclude: set[str]
) -> PlotId | None:
    """Closest unowned land plot to ``(target_x, target_y)``; deterministic tiebreak."""
    candidates: list[tuple[int, int, PlotId]] = []
    for plot in world.plots.values():
        if plot.owner is not None:
            continue
        if not terrain_allows_workshop(plot.terrain):
            continue
        if str(plot.plot_id) in exclude:
            continue
        d = abs(plot.x - target_x) + abs(plot.y - target_y)
        candidates.append((d, str(plot.plot_id), plot.plot_id))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def _instance_complete(world: World, building_id: str, party: PartyId, plot_id: PlotId, label: str) -> str:
    """Drop a fully-built workshop instance onto a plot (bypasses the build pipeline)."""
    world.next_building_instance_seq += 1
    instance_id = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": instance_id,
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": building_id,
            "label": label,
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    world.building_maintenance[instance_id] = {
        "due_at_tick": int(world.tick) + 7_200,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }
    return instance_id


def seed_npc_energy(world: World, *, starting_cash_cents: int | None = None) -> list[str]:
    """Spawn the named NPC energy companies if missing. Returns list of newly created ids."""
    if world.scenario_id != "genesis":
        return []
    cash_cents = (
        starting_cash_cents if starting_cash_cents is not None else NPC_ENERGY_STARTING_CASH_CENTS
    )
    w_, h_ = _bounds(world)
    cx, cy = w_ // 2, h_ // 2
    targets = [
        (cx - _POWER_STAGGER_TILES // 2, cy - _POWER_STAGGER_TILES // 4),
        (cx + _POWER_STAGGER_TILES // 2, cy + _POWER_STAGGER_TILES // 4),
    ]
    created: list[str] = []
    exclude: set[str] = set()
    for energy_id, (tx, ty) in zip(NPC_ENERGY_IDS, targets):
        if energy_id in world.parties:
            continue
        plot_id = _pick_central_inland_plot(world, tx, ty, exclude=exclude)
        if plot_id is None:
            continue
        exclude.add(str(plot_id))
        plot = world.plots[plot_id]
        world.parties.add(energy_id)
        world.reputation[str(energy_id)] = {"honored": 0, "breached": 0}
        world.party_display_names[str(energy_id)] = NPC_ENERGY_DISPLAY_NAMES.get(
            str(energy_id), str(energy_id)
        )
        acct = party_cash_account(energy_id)
        world.ledger.ensure_account(acct)
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=cash_cents,
        )
        if isinstance(tr, MoneyErr):
            continue
        plot.owner = energy_id
        plot.surveyed = True
        _instance_complete(
            world,
            "power_shed",
            energy_id,
            plot_id,
            f"Power shed ({NPC_ENERGY_DISPLAY_NAMES[str(energy_id)]})",
        )
        # Seed a small coal buffer so they can run on day 1.
        ad = world.inventory.add(energy_id, MaterialId("coal"), NPC_ENERGY_COAL_PER_DAY * 2)
        if isinstance(ad, MatterErr):
            continue
        # Make sure the Tier-1 recipe book is seeded, then ensure the two
        # power-generation recipes are available.
        from realm.world import ensure_party_recipe_book

        book = ensure_party_recipe_book(world, energy_id)
        book.add("coal_generator")
        book.add("mine_coal")
        created.append(str(energy_id))
        log_event(
            world,
            "npc_energy_seeded",
            f"NPC energy {energy_id} placed on {plot_id} with completed power_shed",
            party=str(energy_id),
            plot_id=str(plot_id),
            x=int(plot.x),
            y=int(plot.y),
        )
    return created


# ────────────────────────── daily action loop ──────────────────────────


def _home_plot(world: World, party: PartyId) -> PlotId | None:
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) != "power_shed":
            continue
        return PlotId(str(row.get("plot_id") or ""))
    return None


def _coal_buffer_target(world: World, party: PartyId) -> int:
    return NPC_ENERGY_COAL_PER_DAY * NPC_ENERGY_TARGET_COAL_DAYS


def tick_npc_energy(world: World) -> None:
    """Once per game-day: top up coal, run a coal_generator batch, list electricity."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    coal_mid = MaterialId("coal")
    for party in NPC_ENERGY_IDS:
        if party not in world.parties:
            continue
        plot_id = _home_plot(world, party)
        if plot_id is None:
            continue
        # 1. Top up coal if thin.
        have_coal = int(world.inventory.qty(party, coal_mid))
        target = _coal_buffer_target(world, party)
        if have_coal < target:
            need = target - have_coal
            ceiling = max(1, int(exchange_ask_cents(coal_mid)) * 110 // 100)
            market_buy(world, party, coal_mid, need, max_price_per_unit_cents=ceiling)
        # 2. Fire one production batch (idempotent if already running).
        start_production_on_plot(world, party, plot_id, "coal_generator")
        # 3. Surplus is exported to the regional grid on coal_generator completion (no commodity listing).

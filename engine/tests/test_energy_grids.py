"""Sprint 3 — Phase A · regional energy grids.

Covers:
- ``power_shed`` coverage radius (Manhattan 12).
- ``start_production`` fails for electricity recipes off-grid with no
  staged electricity to draw from.
- ``start_production`` succeeds on-grid (electricity input waived).
- Shipped electricity satisfies the off-grid case via staged plot inventory.
- Staged electricity dissipates after its spoilage interval.
- Genesis bootstrap seeds 2 NPC energy companies with completed power_sheds.
"""

from __future__ import annotations

from realm.energy import (
    POWER_COVERAGE_RADIUS,
    is_plot_powered,
    recompute_powered_plots,
)
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import Inventory, MatterErr
from realm.ledger import (
    Ledger,
    MoneyErr,
    party_cash_account,
    system_reserve_account,
)
from realm.materials import MATERIALS
from realm.production import start_production
from realm.spoilage import tick_material_spoilage
from realm.terrain import Terrain
from realm.world import Plot, SubsurfaceRoll, World, bootstrap_genesis


def _build_world(*, width: int = 40, height: int = 30) -> tuple[World, PartyId]:
    sub = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
    )
    plots: dict[PlotId, Plot] = {}
    for y in range(height):
        for x in range(width):
            pid = PlotId(f"p-{x}-{y}")
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=Terrain.PLAINS,
                owner=None,
                subsurface=sub,
                surveyed=True,
            )
    world = World(
        seed=42,
        tick=0,
        plots=plots,
        ledger=Ledger(),
        inventory=Inventory(),
        parties=set(),
        scenario_id="testbed",
        use_plot_output_logistics=True,
    )
    assert not isinstance(world.ledger.seed_system_reserve(10_000_000_000), MoneyErr)
    party = PartyId("alice")
    world.parties.add(party)
    world.ledger.ensure_account(party_cash_account(party))
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=5_000_000,
    )
    world.reputation[str(party)] = {"honored": 0, "breached": 0}
    return world, party


def _claim(world: World, party: PartyId, plot_id: PlotId) -> None:
    plot = world.plots[plot_id]
    plot.owner = party
    plot.surveyed = True


def _install_power_shed(world: World, party: PartyId, plot_id: PlotId, *, warm: bool = True) -> str:
    """Drop a completed ``power_shed`` on the plot; optionally pre-warm past the warmup window."""
    from realm.energy import POWER_BUILDING_WARMUP_TICKS

    world.next_building_instance_seq += 1
    iid = f"b{world.next_building_instance_seq:06d}"
    completes = (
        int(world.tick) - POWER_BUILDING_WARMUP_TICKS - 1
        if warm
        else int(world.tick)
    )
    world.plot_buildings.append(
        {
            "instance_id": iid,
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": "power_shed",
            "label": "power_shed",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": completes,
        }
    )
    world.building_maintenance[iid] = {
        "due_at_tick": int(world.tick) + 7_200,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }
    # Force a recompute so the cache reflects the new source.
    recompute_powered_plots(world)
    return iid


def _install_kiln(world: World, party: PartyId, plot_id: PlotId) -> str:
    world.next_building_instance_seq += 1
    iid = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": iid,
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": "kiln_shed",
            "label": "kiln_shed",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    world.building_maintenance[iid] = {
        "due_at_tick": int(world.tick) + 7_200,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }
    return iid


def _give(world: World, party: PartyId, mat: str, qty: int) -> None:
    res = world.inventory.add(party, MaterialId(mat), qty)
    assert not isinstance(res, MatterErr)


# ───────────────────────── tests ─────────────────────────


def test_power_shed_covers_nearby_plots() -> None:
    world, party = _build_world()
    shed_plot = PlotId("p-10-10")
    _claim(world, party, shed_plot)
    _install_power_shed(world, party, shed_plot)

    # Inside radius (Manhattan 10 ≤ 12).
    assert is_plot_powered(world, PlotId("p-15-15"))
    # On the boundary (Manhattan exactly 12).
    assert is_plot_powered(world, PlotId("p-22-10"))
    # Just outside (Manhattan 13).
    assert not is_plot_powered(world, PlotId("p-23-10"))
    # Far away (Manhattan 30).
    assert not is_plot_powered(world, PlotId("p-25-25"))


def test_production_fails_without_power() -> None:
    world, party = _build_world()
    # Workshop plot has a kiln_shed but no power source anywhere.
    plot = PlotId("p-30-25")
    _claim(world, party, plot)
    _install_kiln(world, party, plot)
    _give(world, party, "clay", 4)
    _give(world, party, "coal", 2)
    r = start_production(world, party, plot, "kiln_brick")
    assert not r["ok"], r
    assert "no power source" in r["reason"]


def test_production_succeeds_with_power() -> None:
    world, party = _build_world()
    plot = PlotId("p-10-10")
    _claim(world, party, plot)
    _install_kiln(world, party, plot)
    # Power source adjacent (in coverage).
    shed_plot = PlotId("p-15-12")
    _claim(world, party, shed_plot)
    _install_power_shed(world, party, shed_plot)
    _give(world, party, "clay", 4)
    _give(world, party, "coal", 2)
    r = start_production(world, party, plot, "kiln_brick")
    assert r["ok"], r


def test_shipped_electricity_powers_plot() -> None:
    world, party = _build_world()
    plot = PlotId("p-30-25")
    _claim(world, party, plot)
    _install_kiln(world, party, plot)
    _give(world, party, "clay", 4)
    _give(world, party, "coal", 2)
    # Sprint 6 — Phase D.1: electricity is sourced from party inventory now.
    _give(world, party, "electricity", 2)
    r = start_production(world, party, plot, "kiln_brick")
    assert r["ok"], r


def test_electricity_spoils_if_unused() -> None:
    world, party = _build_world()
    plot = PlotId("p-5-5")
    _claim(world, party, plot)
    from realm.plot_logistics import plot_output_qty, try_add_plot_output

    res = try_add_plot_output(world, plot, party, MaterialId("electricity"), 3)
    assert not isinstance(res, MatterErr)
    interval = MATERIALS[MaterialId("electricity")].spoilage_interval_ticks
    assert interval > 0
    starting = plot_output_qty(world, plot, MaterialId("electricity"))
    # Advance through several intervals; electricity dissipates deterministically.
    for _ in range(starting + 1):
        world.tick += interval
        tick_material_spoilage(world)
    assert plot_output_qty(world, plot, MaterialId("electricity")) == 0
    # Conservation: every dissipated unit ended up as dissipated_energy on the same plot.
    diss = plot_output_qty(world, plot, MaterialId("dissipated_energy"))
    assert diss >= starting


def test_npc_energy_companies_at_spawn() -> None:
    w = bootstrap_genesis(
        seed=42,
        grid_width=48,
        grid_height=36,
        settler_count=4,
        starting_cash_cents=1_000_000,
    )
    from realm.genesis_energy import NPC_ENERGY_IDS

    seeded = [pid for pid in NPC_ENERGY_IDS if pid in w.parties]
    assert len(seeded) >= 2, f"expected ≥2 NPC energy companies, got {seeded}"
    # Each has at least one running power_shed.
    for pid in seeded:
        sheds = [
            row
            for row in w.plot_buildings
            if str(row.get("party")) == str(pid)
            and str(row.get("building_id")) == "power_shed"
        ]
        assert sheds, f"{pid} missing power_shed"

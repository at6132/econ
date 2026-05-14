"""Tier-2 processing chains, new industrial buildings, tool manufacturing."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.production.buildings import BUILDINGS, build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account
from realm.production import start_production
from realm.production.recipes import RECIPES
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
from realm.world import SubsurfaceRoll, bootstrap_frontier, bootstrap_genesis
from turnkey_fixtures import grant_turnkey_self_materials


def _build_and_finish(w, party: PartyId, pid: PlotId, building_id: str) -> dict:
    grant_turnkey_self_materials(w, party, building_id)
    r = build_on_plot(w, party, pid, building_id, build_mode="turnkey")
    assert r["ok"] is True, r
    inst = r["instance_id"]
    for b in w.plot_buildings:
        if b.get("instance_id") == inst:
            b["completes_at_tick"] = -1
            return b
    raise AssertionError(f"missing building row for {building_id}")


def _setup_mountain_plot(w, party: PartyId, pid: PlotId) -> None:
    plot = w.plots[pid]
    plot.terrain = Terrain.MOUNTAIN
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.8,
        copper_ore_grade=0.6,
        clay_grade=0.0,
        coal_grade=0.7,
    )
    assert claim_plot(w, party, pid)["ok"] is True
    assert survey_plot(w, party, pid)["ok"] is True


def test_tier2_recipe_chain_conservation_pig_iron() -> None:
    """smelt_pig_iron consumes 3 iron_ore + 3 coal + 2 limestone, yields 2 pig_iron + 3 slag.

    Conservation holds across the full tick cycle.
    """
    w = bootstrap_frontier(seed=301, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_mountain_plot(w, player, pid)
    _build_and_finish(w, player, pid, "blast_furnace")
    for mid, qty in (
        (MaterialId("iron_ore"), 6),
        (MaterialId("coal"), 6),
        (MaterialId("limestone"), 4),
        (MaterialId("electricity"), 4),
    ):
        ad = w.inventory.add(player, mid, qty)
        assert not isinstance(ad, MatterErr)
    total0 = w.ledger.total_cents()
    iron0 = w.inventory.qty(player, MaterialId("iron_ore"))
    coal0 = w.inventory.qty(player, MaterialId("coal"))
    lime0 = w.inventory.qty(player, MaterialId("limestone"))
    pig0 = w.inventory.qty(player, MaterialId("pig_iron"))
    slag0 = w.inventory.qty(player, MaterialId("slag"))
    r = start_production(w, player, pid, "smelt_pig_iron")
    assert r["ok"] is True and r.get("started") is True, r
    n = RECIPES["smelt_pig_iron"].duration_ticks
    for _ in range(n):
        advance_tick(w)
    assert w.inventory.qty(player, MaterialId("pig_iron")) == pig0 + 2
    assert w.inventory.qty(player, MaterialId("slag")) == slag0 + 3
    assert w.inventory.qty(player, MaterialId("iron_ore")) == iron0 - 3
    assert w.inventory.qty(player, MaterialId("coal")) == coal0 - 3
    assert w.inventory.qty(player, MaterialId("limestone")) == lime0 - 2
    assert w.ledger.total_cents() == total0


def test_blast_furnace_build_deducts_materials() -> None:
    """Turnkey blast_furnace pulls every entry in self_materials from the builder's inventory."""
    w = bootstrap_frontier(seed=302, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_mountain_plot(w, player, pid)
    grant_turnkey_self_materials(w, player, "blast_furnace")
    spec = BUILDINGS["blast_furnace"]
    mats = spec["self_materials"]
    before = {k: w.inventory.qty(player, MaterialId(k)) for k in mats}
    total0 = w.ledger.total_cents()
    r = build_on_plot(w, player, pid, "blast_furnace", build_mode="turnkey")
    assert r["ok"] is True
    for k, v in mats.items():
        assert w.inventory.qty(player, MaterialId(k)) == before[k] - int(v)
    assert w.ledger.total_cents() == total0


def test_tool_manufacturing_chain() -> None:
    """Forge a pick_head, then assemble into a mining_pick — durable tool ready to use."""
    w = bootstrap_frontier(seed=303, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_mountain_plot(w, player, pid)
    _build_and_finish(w, player, pid, "forge_press")
    _build_and_finish(w, player, pid, "tool_workshop")
    for mid, qty in (
        (MaterialId("steel_ingot"), 4),
        (MaterialId("coal"), 4),
        (MaterialId("electricity"), 6),
        (MaterialId("timber"), 4),
    ):
        ad = w.inventory.add(player, mid, qty)
        assert not isinstance(ad, MatterErr)
    total0 = w.ledger.total_cents()
    steel0 = w.inventory.qty(player, MaterialId("steel_ingot"))
    mp0 = w.inventory.qty(player, MaterialId("mining_pick"))
    r = start_production(w, player, pid, "forge_pick_head")
    assert r["ok"] is True, r
    for _ in range(RECIPES["forge_pick_head"].duration_ticks):
        advance_tick(w)
    assert w.inventory.qty(player, MaterialId("pick_head")) >= 2
    assert w.inventory.qty(player, MaterialId("steel_ingot")) == steel0 - 1
    r2 = start_production(w, player, pid, "assemble_mining_pick")
    assert r2["ok"] is True, r2
    for _ in range(RECIPES["assemble_mining_pick"].duration_ticks):
        advance_tick(w)
    assert w.inventory.qty(player, MaterialId("mining_pick")) == mp0 + 1
    assert w.inventory.qty(player, MaterialId("pick_head")) >= 1
    assert w.ledger.total_cents() == total0


def test_new_buildings_on_exchange_have_tier2_materials() -> None:
    """Genesis bootstrap seeds the new Tier-2 raws and tool components onto the exchange book."""
    from realm.economy.markets import best_resting_ask_cents

    w = bootstrap_genesis(seed=304, grid_width=8, grid_height=6, settler_count=0)
    for mid_s in ("pig_iron", "drill_bit", "sulfur_ore", "tin_ore", "pick_head"):
        ask = best_resting_ask_cents(w, MaterialId(mid_s))
        assert ask is not None, f"expected {mid_s} on the exchange"
        assert ask >= 100


def test_pig_iron_recipe_is_known_to_every_party() -> None:
    """smelt_pig_iron must be Tier-1 (no discovery gate) so it ships in the starter book."""
    w = bootstrap_frontier(seed=305, grid_width=4, grid_height=3)
    book = w.party_recipe_books.get("player", set())
    assert "smelt_pig_iron" in book
    assert "assemble_mining_pick" in book
    assert "make_pump_unit" in book
    assert RECIPES["smelt_pig_iron"].requires_discovery is False


def test_tier2_processing_blocked_without_discovery() -> None:
    """make_bronze must remain locked until tin_ore is fully assayed."""
    w = bootstrap_frontier(seed=306, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    _setup_mountain_plot(w, player, pid)
    _build_and_finish(w, player, pid, "foundry")
    for mid, qty in (
        (MaterialId("tin_ingot"), 1),
        (MaterialId("copper_ingot"), 2),
        (MaterialId("electricity"), 2),
    ):
        ad = w.inventory.add(player, mid, qty)
        assert not isinstance(ad, MatterErr)
    r = start_production(w, player, pid, "make_bronze")
    assert r["ok"] is False
    assert r.get("reason") == "recipe not yet discovered"

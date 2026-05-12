"""Genesis scenario — cold-start economy, settlers, population demand."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.ledger import party_cash_account, system_reserve_account
from realm.tick import advance_tick
from realm.world import GENESIS_POP_HUB_CASH_CENTS, bootstrap_genesis


def test_genesis_bootstrap_ledger_conserved() -> None:
    w = bootstrap_genesis(seed=11, grid_width=10, grid_height=8, settler_count=4)
    assert w.ledger.total_cents() == 100_000_000_000
    player = party_cash_account(PartyId("player"))
    assert w.ledger.balance(player) == 1_000_000
    reserved_out = (
        1_000_000  # player
        + 4 * 1_000_000  # settlers
        + 2 * GENESIS_POP_HUB_CASH_CENTS  # pop hubs
        + 88_000  # Tier-3 Margaux (Genesis)
    )
    assert w.ledger.balance(system_reserve_account()) == 100_000_000_000 - reserved_out


def test_genesis_skips_tier1_npc_bootstrap() -> None:
    w = bootstrap_genesis(seed=1, grid_width=6, grid_height=4, settler_count=2)
    assert PartyId("npc_grain_vendor") not in w.parties
    assert PartyId("t1_consumer") not in w.parties
    assert PartyId("genesis_exchange") in w.parties


def test_genesis_many_ticks_money_conserved() -> None:
    w = bootstrap_genesis(seed=2, grid_width=8, grid_height=6, settler_count=3)
    total = w.ledger.total_cents()
    for _ in range(120):
        advance_tick(w)
    assert w.ledger.total_cents() == total


def test_genesis_settlers_build_workshops_over_time() -> None:
    w = bootstrap_genesis(seed=5, grid_width=14, grid_height=10, settler_count=10)
    for _ in range(160):
        advance_tick(w)
    workshops = [
        b
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_")
        and b.get("building_id") in ("strip_mine", "timber_yard", "grain_row")
    ]
    assert len(workshops) >= 3


def test_genesis_margaux_script_opener_by_tick_14() -> None:
    w = bootstrap_genesis(seed=7, grid_width=8, grid_height=6, settler_count=2)
    for _ in range(15):
        advance_tick(w)
    texts = [str(m.get("text", "")).lower() for m in w.npc_messages_to_player]
    assert any("eastern exchange" in t for t in texts)
    assert w.llm_agents.get("llm_margaux", {}).get("genesis_opener_sent") is True


def test_genesis_settler_workshop_diversity_not_all_strip_mines() -> None:
    w = bootstrap_genesis(seed=13, grid_width=22, grid_height=18, settler_count=40)
    for _ in range(120):
        advance_tick(w)
    sm = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "strip_mine"
    )
    ty = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "timber_yard"
    )
    gr = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "grain_row"
    )
    assert sm <= 36, f"expected strip-mine herd softened vs 40 settlers, got {sm}"
    assert ty + gr >= 10, f"expected timber yards + grain rows, ty={ty} gr={gr}"


def test_genesis_coal_asks_return_after_heavy_ticks() -> None:
    from realm.markets import best_resting_ask_cents

    w = bootstrap_genesis(seed=9, grid_width=12, grid_height=10, settler_count=12)
    for _ in range(220):
        advance_tick(w)
    px = best_resting_ask_cents(w, MaterialId("coal"))
    assert px is not None


def test_genesis_world_feed_emits_by_tick_16() -> None:
    w = bootstrap_genesis(seed=909, grid_width=6, grid_height=5, settler_count=2)
    for _ in range(17):
        advance_tick(w)
    assert any(e.get("kind") == "world_feed" for e in w.event_log)


def test_genesis_supply_contract_triggers_with_listed_coal() -> None:
    from realm.inventory import MatterErr
    from realm.markets import place_sell_order

    w = bootstrap_genesis(seed=414, grid_width=8, grid_height=6, settler_count=2)
    p = PartyId("player")
    coal = MaterialId("coal")
    ad = w.inventory.add(p, coal, 20)
    assert not isinstance(ad, MatterErr)
    assert place_sell_order(w, p, coal, 12, 58)["ok"] is True
    for _ in range(35):
        advance_tick(w)
    proposed = [
        c
        for c in w.contracts
        if c.get("kind") == "supply"
        and c.get("status") == "proposed"
        and str(c.get("supplier")) == "player"
    ]
    assert len(proposed) >= 1


def test_genesis_settlers_build_secondary_workshops() -> None:
    w = bootstrap_genesis(seed=17, grid_width=24, grid_height=20, settler_count=35)
    for _ in range(220):
        advance_tick(w)
    secondary = {
        "power_shed",
        "wood_shop",
        "gristmill",
        "kiln_shed",
        "foundry",
        "stone_works",
    }
    n = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_")
        and str(b.get("building_id", "")) in secondary
    )
    assert n >= 8, f"expected settlers to add processing workshops, got {n}"


def test_genesis_subsurface_correlation_mountains_richer_in_iron() -> None:
    """Terrain-correlated rolls bias mountains toward higher iron vs the rest of the grid."""
    from realm.world import generate_plots

    plots = generate_plots(seed=42, width=60, height=45, correlate_subsurface=True)
    ir_mountain = [
        p.subsurface.iron_ore_grade for p in plots.values() if p.terrain.value == "mountain"
    ]
    ir_other = [
        p.subsurface.iron_ore_grade for p in plots.values() if p.terrain.value != "mountain"
    ]
    assert len(ir_mountain) > 50 and len(ir_other) > 100
    assert sum(ir_mountain) / len(ir_mountain) > sum(ir_other) / len(ir_other)

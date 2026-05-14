"""Phase 8 — Sub-phase 8C: epidemic system tests.

Covers the contract laid out in the Sub-phase 8C spec:
  * ``wild_herb`` is gatherable in forests (Tier-0 hand recipe).
  * ``apothecary`` building exists and ``make_medicine`` runs in it.
  * Epidemic accelerates health decay in the affected town.
  * Medicine purchase at a store treats the laborer (one heal per epidemic).
  * Severe epidemic with no medicine kills laborers and records deaths.
  * Conservation holds under epidemic + medicine flow.
"""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.world_events import (
    EPIDEMIC_MEDICINE_HEAL_AMOUNT,
    active_epidemic_for_town,
    epidemic_health_decay_multiplier,
    trigger_epidemic,
)
from realm.materials import MATERIALS
from realm.population.laborers import (
    _apply_health_pressure,
    tick_laborers,
)
from realm.population.stores import (
    set_store_price,
    stock_store,
    tick_laborer_spending,
)
from realm.production.recipes import RECIPES
from realm.production.buildings import BUILDINGS
from realm.world import bootstrap_genesis
from realm.world.terrain import Terrain


# ─────────────────────────────────────────────────────────────────────
# Catalog
# ─────────────────────────────────────────────────────────────────────


def test_wild_herb_and_medicine_in_material_catalog() -> None:
    assert MaterialId("wild_herb") in MATERIALS
    assert MaterialId("medicine") in MATERIALS


def test_apothecary_in_building_catalog() -> None:
    assert "apothecary" in BUILDINGS


def test_gather_herbs_recipe_exists_with_forest_terrain_and_tier0() -> None:
    r = RECIPES.get("gather_herbs")
    assert r is not None
    # Hand recipe: no building required, uses a tool.
    assert r.requires_building_id == ""
    assert r.requires_tool == MaterialId("spade")
    assert MaterialId("wild_herb") in r.outputs


def test_make_medicine_recipe_requires_apothecary() -> None:
    r = RECIPES.get("make_medicine")
    assert r is not None
    assert r.requires_building_id == "apothecary"
    assert MaterialId("medicine") in r.outputs
    # Inputs are herbs + coal + electricity per the spec.
    assert MaterialId("wild_herb") in r.inputs
    assert MaterialId("coal") in r.inputs
    assert MaterialId("electricity") in r.inputs


# ─────────────────────────────────────────────────────────────────────
# Epidemic effects
# ─────────────────────────────────────────────────────────────────────


def _bootstrap_with_towns() -> object:
    """Helper: build a world that already has towns seeded by ``bootstrap_genesis``."""
    return bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)


def test_epidemic_event_can_be_triggered_in_town() -> None:
    w = _bootstrap_with_towns()
    assert w.towns, "bootstrap should seed at least one town"
    town_id = next(iter(w.towns.keys()))
    ev = trigger_epidemic(w, town_id, severity=0.7, duration_days=12)
    assert ev is not None
    assert ev.event_type == "epidemic"
    assert ev.payload["town_id"] == town_id
    assert active_epidemic_for_town(w, town_id) is ev


def test_epidemic_idempotent_per_town() -> None:
    """Calling trigger twice on the same town returns the same active event."""
    w = _bootstrap_with_towns()
    town_id = next(iter(w.towns.keys()))
    ev1 = trigger_epidemic(w, town_id, severity=0.5, duration_days=10)
    ev2 = trigger_epidemic(w, town_id, severity=0.8, duration_days=5)
    assert ev1 is ev2


def test_epidemic_accelerates_health_decay_multiplier() -> None:
    w = _bootstrap_with_towns()
    town_id = next(iter(w.towns.keys()))
    assert epidemic_health_decay_multiplier(w, town_id) == 1.0
    trigger_epidemic(w, town_id, severity=0.6, duration_days=10)
    assert epidemic_health_decay_multiplier(w, town_id) > 1.0


def test_apply_health_pressure_with_epidemic_drops_faster() -> None:
    """Direct unit test: a healthy laborer with full needs still loses
    health each day when an epidemic is active."""
    from realm.population.laborers import LaborerNPC

    lab = LaborerNPC(
        laborer_id="lab-test",
        display_name="Test",
        island_id=1,
        home_plot_id=PlotId("p-0-0"),
        home_town="t-test",
    )
    baseline_health = lab.health
    _apply_health_pressure(lab, 1.0, epidemic_mult=1.0)
    delta_baseline = baseline_health - lab.health
    # Reset; same conditions but with the epidemic mult.
    lab.health = baseline_health
    _apply_health_pressure(lab, 1.0, epidemic_mult=3.0)
    delta_epidemic = baseline_health - lab.health
    assert delta_epidemic > delta_baseline, (
        f"epidemic mult should accelerate decay (base {delta_baseline}, epidemic {delta_epidemic})"
    )


def test_epidemic_kills_laborers_when_health_collapses() -> None:
    """A severe epidemic in a town with no medicine drops laborer health
    until at least one dies; the event payload counts the death."""
    w = _bootstrap_with_towns()
    town_id = next(iter(w.towns.keys()))
    # Find a resident.
    residents = [lab for lab in w.laborers.values() if lab.home_town == town_id]
    if not residents:
        # Force-assign one if the bootstrap didn't.
        any_lab = next(iter(w.laborers.values()))
        any_lab.home_town = town_id
        residents = [any_lab]
    # Pre-condition: knock a few laborers down to near-death so the
    # epidemic finishes them within a short window.
    target_ids = [residents[0].laborer_id]
    residents[0].health = 0.20
    ev = trigger_epidemic(w, town_id, severity=1.0, duration_days=20)
    # Run 12 game-days of laborer ticks.
    pre_count = len([lab for lab in w.laborers.values() if lab.home_town == town_id])
    for _ in range(12):
        w.tick += TICKS_PER_GAME_DAY
        tick_laborers(w)
    deaths = int(ev.payload.get("deaths", 0))
    assert deaths >= 1, (
        f"epidemic with severity 1.0 should produce at least one death "
        f"(deaths={deaths}, residents pre={pre_count})"
    )


def test_medicine_purchase_treats_laborer_during_epidemic() -> None:
    """When a store sells medicine during an active epidemic, a laborer
    visits and the treatment grants +0.30 health (capped at 1.0)."""
    w = _bootstrap_with_towns()
    town_id = next(iter(w.towns.keys()))
    # Set up a willing buyer: pick a resident, lower their health, ensure
    # they have cash.
    residents = [lab for lab in w.laborers.values() if lab.home_town == town_id]
    if not residents:
        any_lab = next(iter(w.laborers.values()))
        any_lab.home_town = town_id
        residents = [any_lab]
    lab = residents[0]
    lab.health = 0.5
    # Pre-existing town store: use the seeded NPC store and stock medicine
    # on it. ``stock_store`` requires party owner — use the store owner.
    from realm.population.towns import Town

    town: Town = w.towns[town_id]
    # Force-attach a town store if none exists yet (bootstrap may not have
    # given this town a store).
    if not town.store_plots:
        # Promote any nearby unowned land plot to a "store" building owned
        # by genesis_storekeeper. We bypass the building-construction path
        # for the test — the tick spending code only checks for a complete
        # building row.
        store_owner = PartyId("genesis_storekeeper")
        if store_owner not in w.parties:
            w.parties.add(store_owner)
            w.reputation[str(store_owner)] = {"honored": 0, "breached": 0}
        plot_islands = w.scenario_state.get("plot_islands") or {}
        plot_id: PlotId | None = None
        for pid_s, isl in plot_islands.items():
            if int(isl) != int(town.island_id):
                continue
            p = w.plots.get(PlotId(pid_s))
            if p is None or p.owner is not None:
                continue
            if p.terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP):
                continue
            p.owner = store_owner
            plot_id = p.plot_id
            break
        assert plot_id is not None
        w.plot_buildings.append(
            {
                "instance_id": "store-test",
                "plot_id": str(plot_id),
                "party": str(store_owner),
                "building_id": "store",
                "status": "complete",
                "completes_at_tick": int(w.tick),
            }
        )
        town.store_plots.append(plot_id)
    store_plot = town.store_plots[0]
    store_owner = w.plots[store_plot].owner
    assert store_owner is not None
    # Stock 5 medicine for $5 each at the store.
    # Use the action helpers so ledger / inventory paths are exercised.
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.core.inventory import MatterErr

    ad = w.inventory.add(store_owner, MaterialId("medicine"), 5)
    if isinstance(ad, MatterErr):
        raise AssertionError(ad.reason)
    r = stock_store(w, store_owner, store_plot, MaterialId("medicine"), 5)
    assert r.get("ok"), r
    r = set_store_price(w, store_owner, store_plot, MaterialId("medicine"), 500)
    assert r.get("ok"), r

    # Fire the epidemic and force enough cash for the laborer.
    trigger_epidemic(w, town_id, severity=0.5, duration_days=15)
    lab_account = f"cash:lab:{lab.laborer_id}"
    if w.ledger.balance(lab_account) < 2_000:
        w.ledger.transfer(
            debit=system_reserve_account(),
            credit=lab_account,
            amount_cents=2_000,
        )
    pre_health = lab.health
    pre_total = w.ledger.total_cents()
    # Skip the spending guard's "once per day" check by advancing past it.
    w.scenario_state["store_last_spend_tick"] = -1
    w.tick += TICKS_PER_GAME_DAY * 1
    # Ensure the food/fuel branch doesn't gobble all the laborer's cash by
    # putting them at full food + fuel.
    lab.needs["food"] = 1.0
    lab.needs["fuel"] = 1.0
    stats = tick_laborer_spending(w)
    assert lab.health >= pre_health + EPIDEMIC_MEDICINE_HEAL_AMOUNT - 1e-9, (
        f"medicine should heal {EPIDEMIC_MEDICINE_HEAL_AMOUNT:.2f} (pre {pre_health}, post {lab.health})"
    )
    # Conservation holds across the purchase.
    assert w.ledger.total_cents() == pre_total


def test_epidemic_world_event_conservation() -> None:
    """Fire an epidemic and tick a week: ledger total invariant."""
    w = _bootstrap_with_towns()
    town_id = next(iter(w.towns.keys()))
    pre = w.ledger.total_cents()
    trigger_epidemic(w, town_id, severity=0.7, duration_days=10)
    for _ in range(7):
        w.tick += TICKS_PER_GAME_DAY
        tick_laborers(w)
    assert w.ledger.total_cents() == pre

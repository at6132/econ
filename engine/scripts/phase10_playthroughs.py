"""Phase 10 — Step 0B headless playthroughs (fast diagnostic version).

For each scenario, set up the world state and probe each action endpoint
synchronously to see exactly which steps fail. Skips long tick loops and
focuses on identifying gaps in current Phase 9 surface area.
"""

from __future__ import annotations

import inspect
import os
import sys
import traceback
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "tests"))


def _grant_turnkey(world, party, building_id, count=1):
    from realm.production.buildings import BUILDINGS
    from realm.core.ids import MaterialId
    from realm.core.inventory import MatterErr

    spec = BUILDINGS.get(building_id)
    if not spec or str(spec.get("kind")) != "contracted":
        return
    for mid_s, qty in (spec.get("self_materials") or {}).items():
        ad = world.inventory.add(party, MaterialId(str(mid_s)), int(qty) * int(count))
        assert not isinstance(ad, MatterErr), ad


def _try(label, fn):
    try:
        return label, fn()
    except Exception as e:
        return label, f"EXC {type(e).__name__}: {e}"


def _record(scenario, lines):
    print(f"\n=== {scenario} ===")
    for label, result in lines:
        print(f"  • {label}")
        if isinstance(result, dict):
            for k, v in result.items():
                print(f"      {k}: {v}")
        elif isinstance(result, list) and result and isinstance(result[0], (str, int)):
            print(f"      {result[:6]}")
        else:
            print(f"      {result}")


def world_small():
    """Smaller bootstrap for fast probing."""
    from realm.world import bootstrap_genesis

    return bootstrap_genesis(seed=42)


def coal_miner():
    from realm.actions.plot_actions import claim_plot
    from realm.actions.business_actions import register_business
    from realm.core.ids import PartyId, PlotId
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.production.buildings import BUILDINGS, build_on_plot

    w = world_small()
    party = PartyId("coal_baron")
    w.parties.add(party)
    w.reputation[str(party)] = {"honored": 0, "breached": 0}
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=10_000_000)

    pid = None
    for p_id, p in w.plots.items():
        if p.owner is None and p.terrain.value == "mountain" and p.subsurface.coal_grade > 0.4:
            pid = p_id
            break

    lines = []
    lines.append(_try("find unowned mountain plot w/ coal", lambda: f"found={pid is not None} pid={pid}"))

    if pid:
        lines.append(_try("claim_plot", lambda: claim_plot(w, party, pid)))
        _grant_turnkey(w, party, "strip_mine")
        lines.append(_try("build strip_mine", lambda: build_on_plot(w, party, pid, "strip_mine", build_mode="turnkey")))
        # Now try to register a business with PLOTS (Phase 10 shape)
        sig = inspect.signature(register_business)
        has_plot_ids = "plot_ids" in sig.parameters
        lines.append(_try("register_business signature has plot_ids", lambda: has_plot_ids))
        if has_plot_ids:
            lines.append(_try("register_business (extended)",
                              lambda: register_business(w, party, name="Coal Baron Mining Co",
                                                        type_tag="mining", description="",
                                                        plot_ids=[pid], public=True)))
        else:
            lines.append(_try("register_business (legacy 4-arg)",
                              lambda: register_business(w, party, "Coal Baron Mining Co", "")))

    # Inspect: do we have a `world.businesses` dict (Phase 10)?
    lines.append(_try("world.businesses attr exists",
                      lambda: hasattr(w, "businesses")))
    lines.append(_try("world.business_registry size",
                      lambda: len(w.business_registry)))
    return lines


def shipping_company():
    from realm.actions.plot_actions import claim_plot
    from realm.core.ids import MaterialId, PartyId
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.production.buildings import build_on_plot
    from realm.production.recipe_sites import plot_is_coastal

    w = world_small()
    party = PartyId("shipper_test")
    w.parties.add(party)
    w.reputation[str(party)] = {"honored": 0, "breached": 0}
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=10_000_000)

    coastal_pid = None
    for p_id, p in w.plots.items():
        if p.owner is None and plot_is_coastal(w, p):
            coastal_pid = p_id
            break

    lines = []
    lines.append(_try("find unowned coastal plot",
                      lambda: f"found={coastal_pid is not None} pid={coastal_pid}"))

    seeded_routes = w.scenario_state.get("route_operators") or {}
    lines.append(_try("seeded route count at bootstrap",
                      lambda: sum(len(e) for e in seeded_routes.values())))
    lines.append(_try("voyage_history attr exists",
                      lambda: bool(w.scenario_state.get("voyage_history") is not None)))
    lines.append(_try("small_vessel material exists",
                      lambda: ("small_vessel" in {str(m) for m in w.inventory.qty.__self__.stock} if False else "?"))) # noqa
    # Actually check:
    from realm.materials import MATERIALS
    lines.append(_try("small_vessel material in MATERIALS",
                      lambda: "small_vessel" in {str(k) for k in MATERIALS.keys()}))
    return lines


def retail_store():
    from realm.actions.plot_actions import claim_plot
    from realm.core.ids import PartyId
    from realm.core.ledger import party_cash_account, system_reserve_account

    w = world_small()
    party = PartyId("merchant_test")
    w.parties.add(party)
    w.reputation[str(party)] = {"honored": 0, "breached": 0}
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=5_000_000)

    lines = []
    lines.append(_try("town count at bootstrap", lambda: len(w.towns)))
    lines.append(_try("first town id",
                      lambda: next(iter(w.towns.values())).town_id if w.towns else None))
    # Check if NPC store seeded
    npc_stores = w.scenario_state.get("starting_npc_store_plots") or []
    lines.append(_try("starting NPC store plots", lambda: len(npc_stores)))
    # Check store_inventories at first NPC store
    if npc_stores:
        first_store_pid = npc_stores[0]
        lines.append(_try("first NPC store inventory keys",
                          lambda: list((w.store_inventories.get(str(first_store_pid)) or {}).keys())))
    return lines


def land_speculator():
    from realm.actions.plot_actions import claim_plot, list_survey_report, survey_plot
    from realm.core.ids import PartyId
    from realm.core.ledger import party_cash_account, system_reserve_account

    w = world_small()
    party = PartyId("speculator_test")
    w.parties.add(party)
    w.reputation[str(party)] = {"honored": 0, "breached": 0}
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=20_000_000)

    plots = []
    for p_id, p in w.plots.items():
        if p.owner is None and p.terrain.value not in ("water_deep", "water_shallow"):
            cr = claim_plot(w, party, p_id)
            if cr.get("ok"):
                plots.append(p_id)
                if len(plots) >= 5:
                    break

    lines = []
    lines.append(_try("claimed N plots", lambda: len(plots)))
    surveys = []
    for pid in plots:
        sr = survey_plot(w, party, pid)
        surveys.append((str(pid), sr.get("ok"), sr.get("reason") if not sr.get("ok") else None))
    lines.append(_try("survey results", lambda: surveys))
    return lines


def apothecary():
    from realm.actions.plot_actions import claim_plot
    from realm.core.ids import MaterialId, PartyId
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.production.buildings import build_on_plot
    from realm.production.recipes import RECIPES

    w = world_small()
    party = PartyId("apothecary_test")
    w.parties.add(party)
    w.reputation[str(party)] = {"honored": 0, "breached": 0}
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=10_000_000)

    pid = None
    for p_id, p in w.plots.items():
        if p.owner is None and p.terrain.value == "forest":
            pid = p_id
            break

    lines = []
    lines.append(_try("forest plot found", lambda: pid is not None))
    if pid:
        lines.append(_try("claim_plot", lambda: claim_plot(w, party, pid)))
        _grant_turnkey(w, party, "apothecary")
        lines.append(_try("build apothecary", lambda: build_on_plot(w, party, pid, "apothecary", build_mode="turnkey")))

    medicine_recipes = [rid for rid, r in RECIPES.items() if "medicine" in {str(m) for m in (r.outputs or {}).keys()}]
    herb_recipes = [rid for rid, r in RECIPES.items() if "wild_herb" in {str(m) for m in (r.outputs or {}).keys()}]
    lines.append(_try("recipes outputting medicine", lambda: medicine_recipes))
    lines.append(_try("recipes outputting wild_herb", lambda: herb_recipes))
    lines.append(_try("apothecary in BUILDINGS",
                      lambda: __import__("realm.production.buildings", fromlist=["BUILDINGS"]).BUILDINGS["apothecary"].get("kind")))
    lines.append(_try("laboratory in BUILDINGS",
                      lambda: "laboratory" in __import__("realm.production.buildings", fromlist=["BUILDINGS"]).BUILDINGS))
    return lines


def chemistry_check():
    """Phase 10 specific: are elements/reactions defined?"""
    lines = []
    try:
        from realm.science import elements as _el  # type: ignore

        lines.append(_try("realm.science.elements importable", lambda: True))
        lines.append(_try("ELEMENTS dict exists",
                          lambda: hasattr(_el, "ELEMENTS")))
    except ImportError:
        lines.append(_try("realm.science.elements importable", lambda: False))
    try:
        from realm.science import reactions as _rx  # type: ignore

        lines.append(_try("KNOWN_REACTIONS dict exists",
                          lambda: hasattr(_rx, "KNOWN_REACTIONS")))
    except ImportError:
        lines.append(_try("realm.science.reactions importable", lambda: False))
    return lines


def construction_check():
    """Phase 10 specific: are construction firms/orders defined?"""
    lines = []
    try:
        from realm.contracts import construction_orders as _co  # type: ignore

        lines.append(_try("realm.contracts.construction_orders importable", lambda: True))
    except ImportError:
        lines.append(_try("realm.contracts.construction_orders importable", lambda: False))
    try:
        from realm.genesis import construction_firms as _cf  # type: ignore

        lines.append(_try("realm.genesis.construction_firms importable", lambda: True))
    except ImportError:
        lines.append(_try("realm.genesis.construction_firms importable", lambda: False))
    return lines


def world_layout_check():
    """Phase 10 specific: continental layout?"""
    from realm.world import bootstrap_genesis

    w = world_small()
    lines = []
    lines.append(_try("plot_islands count", lambda: len({int(v) for v in (w.scenario_state.get("plot_islands") or {}).values()})))
    lines.append(_try("landmass_id attr exists", lambda: hasattr(w, "landmass_id")))
    lines.append(_try("landmass_type attr exists", lambda: hasattr(w, "landmass_type")))
    # Check current grid
    max_x = max(p.x for p in w.plots.values())
    max_y = max(p.y for p in w.plots.values())
    lines.append(_try("grid bounds (w x h)", lambda: f"{max_x+1} x {max_y+1}"))
    lines.append(_try("plot count", lambda: len(w.plots)))
    return lines


if __name__ == "__main__":
    print("Phase 10 — Step 0B headless diagnostic playthroughs (seed=42)")
    print("=" * 60)
    _record("0. World layout (current state)", world_layout_check())
    _record("1. Coal miner → vertical integrator", coal_miner())
    _record("2. Shipping company", shipping_company())
    _record("3. Retail store", retail_store())
    _record("4. Land speculator", land_speculator())
    _record("5. Apothecary", apothecary())
    _record("6. Chemistry surface check", chemistry_check())
    _record("7. Construction surface check", construction_check())
    print("\n" + "=" * 60)
    print("Done.")

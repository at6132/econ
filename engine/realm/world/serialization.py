"""Public-dict serialization for ``World``: the JSON DTOs returned by
``/world*`` routes.

Functions take ``world: World`` (and sometimes ``party``) and return
JSON-serializable ``dict``s. They never mutate state.

Endpoints + payload responsibilities (see ``routes_world.py``):

* ``world_public_dict``  — legacy "everything in one shot" (heavy; ~27 MB on
                            Genesis). Kept for back-compat; new code should
                            prefer the split payloads below.
* ``world_summary_dict`` — top-bar HUD (tick, cash, counters). Tiny.
* ``world_static_dict``  — read-once tables (recipes, building catalog,
                            chemistry, scenario constants, party names).
* ``world_player_dict``  — everything tied to a single party: inventory,
                            owned plots + subsurface + recipe_ids, accounts,
                            bank rates/loans, in_transit, forward contracts,
                            owned reports, price alerts, active production.
* ``world_plots_dict``   — map-only lean view: terrain / owner / surveyed /
                            powered / population_density / claim_cost_cents.
                            Drops per-cell subsurface and recipe_ids; drops
                            ``world_cells`` on uniform-plot grids.
* ``world_feed_dict``    — event_log + world_feed + npc_messages tails
                            (optionally since ``since_tick``).
* ``world_compact_dict`` — small dev/automation aggregate snapshot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account
from realm.production.recipes import recipe_public_list
from realm.world.terrain import Terrain

if TYPE_CHECKING:  # pragma: no cover - typing only
    from realm.world.world import World


def _world_map_tile_count(world: "World") -> int:
    from realm.world.plot_parcels import world_map_tile_count

    return world_map_tile_count(world)


def _building_maintenance_view(world: "World", row: dict) -> dict:
    """Public DTO for a single building's maintenance state (forwarded to API/UI)."""
    from realm.production.decay import building_maintenance_status

    return building_maintenance_status(world, row)


def _grid_is_uniform(world: "World") -> bool:
    """True when every plot covers exactly one (x, y) cell.

    Used to drop ``world_cells`` lists and ``world_cell_to_plot`` from the
    wire — they're fully derivable from ``(plot.x, plot.y)`` on uniform
    grids (the default Genesis layout)."""
    for p in world.plots.values():
        wc = p.world_cells
        if wc and len(wc) != 1:
            return False
        if wc and (wc[0][0] != p.x or wc[0][1] != p.y):
            return False
    return True


def world_public_dict(world: "World") -> dict:
    """JSON-serializable view for API (hides unsurveyed subsurface).

    Legacy "kitchen-sink" payload. Heavy on Genesis grids; the realtime
    client should poll ``/world/summary`` + ``/world/player`` + ``/world/feed``
    and only request ``/world/map`` after a structural change.
    """
    from realm.actions import hire_catalog_public
    from realm.economy.intel import FREE_MARKET_HISTORY_TICKS
    from realm.economy.markets import market_bids_public, market_book_public
    from realm.infrastructure.power_grid import compute_grid_regions
    from realm.production.buildings import building_catalog_public
    from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
    from realm.core.time_scale import TICKS_PER_GAME_DAY
    from realm.world.world import claim_cost_cents_for_plot

    _regions = compute_grid_regions(world)
    powered_set = {
        pid
        for rid, reg in _regions.items()
        if reg.capacity_per_day > 0 and not rid.startswith("grid_iso_")
        for pid in reg.plot_ids
    }
    density_map = world.scenario_state.get("population_density") or {}
    from realm.world.plot_scale import (
        plot_area_sq_metres,
        plot_grid_side,
        plot_world_cells_tuple,
        plot_world_span,
    )

    uniform = _grid_is_uniform(world)

    plots_out: list[dict] = []
    for p in world.plots.values():
        density = float(density_map.get(str(p.plot_id), 0.0))
        _, _, wt, ht = plot_world_span(p)
        gcw, gch = plot_grid_side(p)
        entry: dict = {
            "id": p.plot_id,
            "x": p.x,
            "y": p.y,
            "terrain": p.terrain.value,
            "world_tiles_w": wt,
            "world_tiles_h": ht,
            "grid_cells_w": gcw,
            "grid_cells_h": gch,
            "area_sq_metres": plot_area_sq_metres(p),
            "owner": p.owner,
            "surveyed": p.surveyed,
            "deep_surveyed": getattr(p, "deep_surveyed", False),
            "powered": str(p.plot_id) in powered_set,
            "population_density": density,
            "claim_cost_cents": claim_cost_cents_for_plot(world, p.plot_id),
        }
        if not uniform:
            entry["world_cells"] = [
                {"x": cx, "y": cy} for cx, cy in plot_world_cells_tuple(p)
            ]
            entry["parcel_shape"] = getattr(p, "parcel_shape", "") or "poly"
        if p.surveyed:
            sub_view: dict[str, float] = {
                "iron_ore_grade": p.subsurface.iron_ore_grade,
                "copper_ore_grade": p.subsurface.copper_ore_grade,
                "clay_grade": p.subsurface.clay_grade,
                "coal_grade": p.subsurface.coal_grade,
                "sulfur_grade": p.subsurface.sulfur_grade,
                "saltpeter_grade": p.subsurface.saltpeter_grade,
                "tin_grade": p.subsurface.tin_grade,
                "lead_grade": p.subsurface.lead_grade,
                "phosphate_grade": p.subsurface.phosphate_grade,
                "silica_grade": p.subsurface.silica_grade,
            }
            if getattr(p, "deep_surveyed", False):
                sub_view["platinum_grade"] = p.subsurface.platinum_grade
                sub_view["oil_shale_grade"] = p.subsurface.oil_shale_grade
                sub_view["rare_earth_grade"] = p.subsurface.rare_earth_grade
            entry["subsurface"] = sub_view
            entry["recipe_ids"] = recipe_ids_on_plot_for_owner(world, p)
        if world.use_plot_output_logistics and p.owner is not None:
            entry["output_stock"] = dict(world.plot_output_stock.get(str(p.plot_id), {}))
        plots_out.append(entry)
    balances = {str(k): v for k, v in world.ledger.snapshot().items()}
    inv: dict[str, dict[str, object]] = {}
    for party, mats in world.inventory.snapshot().items():
        party_inv: dict[str, object] = {}
        for mat, raw in mats.items():
            from realm.core.inventory import _normalize_bucket

            bucket = _normalize_bucket(raw)
            if len(bucket) == 1 and "standard" in bucket:
                party_inv[str(mat)] = int(bucket["standard"])
            elif bucket:
                party_inv[str(mat)] = dict(bucket)
        inv[str(party)] = party_inv

    intel_active = world.tick < world.market_intel_expires_tick
    hist = world.market_history
    if intel_active:
        market_hist_out = list(hist)
    else:
        market_hist_out = list(hist[-FREE_MARKET_HISTORY_TICKS:])

    return {
        "seed": world.seed,
        "tick": world.tick,
        "ticks_per_game_day": TICKS_PER_GAME_DAY,
        "scenario_id": world.scenario_id,
        "world_name": world.world_name,
        "market_intel_expires_tick": world.market_intel_expires_tick,
        "market_intel_active": intel_active,
        "market_history_free_window_ticks": FREE_MARKET_HISTORY_TICKS,
        "uniform_plots": uniform,
        "plots": plots_out,
        # On a uniform grid, ``world_cell_to_plot`` is derivable from (x,y)
        # via ``f"p-{x}-{y}"`` — sending 76800 strings is wasteful. Clients
        # check the ``uniform_plots`` flag and rebuild locally when absent.
        **(
            {}
            if uniform
            else {
                "world_cell_to_plot": dict(
                    world.scenario_state.get("world_cell_to_plot") or {}
                )
            }
        ),
        "balances_cents": balances,
        "inventory": inv,
        "parties": [str(x) for x in world.parties],
        "recipes": recipe_public_list(),
        "active_production": [
            {
                "run_id": a.run_id,
                "party": str(a.party),
                "plot_id": str(a.plot_id),
                "recipe_id": a.recipe_id,
                "ticks_remaining": a.ticks_remaining,
            }
            for a in world.active_production
        ],
        "in_transit": [
            {
                "id": s.shipment_id,
                "shipment_id": s.shipment_id,
                "party": str(s.party),
                "material": str(s.material),
                "qty": s.qty,
                "from_plot_id": str(s.from_plot_id) if s.from_plot_id else None,
                "dest_plot_id": str(s.dest_plot_id),
                "arrive_tick": s.arrive_tick,
            }
            for s in world.in_transit
        ],
        "market_asks": market_book_public(world),
        "market_bids": market_bids_public(world),
        "reputation": dict(world.reputation),
        "contracts": list(world.contracts),
        "event_log": list(world.event_log[-120:]),
        "world_feed_log": list(world.world_feed_log[-1500:]),
        "plot_buildings": [
            {**b, "maintenance": _building_maintenance_view(world, b)}
            for b in world.plot_buildings
        ],
        "stub_hires": list(world.stub_hires),
        "building_catalog": building_catalog_public(),
        "market_history": market_hist_out[-160:],
        "hire_catalog": hire_catalog_public(),
        "llm_agents": [
            {
                "party": pid,
                "display_name": blob.get("display_name", pid),
                "memory_summary": str(blob.get("memory_summary", ""))[:800],
            }
            for pid, blob in sorted(world.llm_agents.items(), key=lambda x: x[0])
        ],
        "npc_messages": list(world.npc_messages_to_player[-48:]),
        "party_display_names": dict(world.party_display_names),
        "llm_session_cost_micro_usd": world.llm_session_cost_micro_usd,
        "llm_session_input_tokens": world.llm_session_input_tokens,
        "llm_session_output_tokens": world.llm_session_output_tokens,
        "deployed_lua": {
            k: {
                "chars": len(v),
                "lines": v.count("\n") + (1 if v else 0),
            }
            for k, v in sorted(world.deployed_lua_sources.items(), key=lambda x: x[0])
        },
        "party_recipe_books": {
            str(k): sorted(v) for k, v in world.party_recipe_books.items()
        },
        "intel_listings": _intel_listings_public(world),
        "player_owned_reports": _player_owned_reports_public(world, PartyId("player")),
        "analytics_purchases": list(world.analytics_purchases[-48:]),
        "business_registry": _business_registry_public(world),
        "player_accounts": _player_accounts_public(world),
        "bank_rates": _bank_rates_public(world),
        "bank_loans": _bank_loans_for_player(world),
        "bank_plot_id": world.scenario_state.get("bank_plot"),
        "road_segments": _road_segments_public(world),
        "player_price_alerts": list(
            (world.scenario_state.get("player_price_alerts") or [])
        ),
        "forward_contracts": _forward_contracts_public(world, PartyId("player")),
        "business_entities": _business_entities_public(world),
        "nascent_settlements": _nascent_settlements_public(world),
        "chemistry_catalog": _chemistry_catalog_public(),
    }


def _player_accounts_public(world: "World") -> list[dict]:
    """Public view of the player's accounts (Sprint 5 — Phase B)."""
    try:
        from realm.core.sub_accounts import party_accounts_view
    except Exception:
        return []
    return party_accounts_view(world, PartyId("player"))


def _bank_rates_public(world: "World") -> dict | None:
    """Public view of the bank's posted rates for the player (Sprint 5 — Phase C)."""
    try:
        from realm.genesis.bank import FIRST_BANK_PARTY_ID, bank_rates_view
    except Exception:
        return None
    if FIRST_BANK_PARTY_ID not in world.parties:
        return None
    return bank_rates_view(world, PartyId("player"))


def _bank_loans_for_player(world: "World") -> list[dict]:
    """Active bank loans for the player (Sprint 5 — Phase C)."""
    try:
        from realm.genesis.bank import active_loans_for_borrower
    except Exception:
        return []
    return active_loans_for_borrower(world, PartyId("player"))


def _road_segments_public(world: "World") -> list[dict]:
    """Public view of every built road segment (Sprint 6 — Phase A)."""
    try:
        from realm.infrastructure.roads import all_roads_public
    except Exception:
        return []
    return all_roads_public(world)


def _business_registry_public(world: "World") -> dict[str, dict]:
    """Public view of registered businesses (Sprint 5 — Phase A)."""
    out: dict[str, dict] = {}
    for pid_s, rec in world.business_registry.items():
        out[str(pid_s)] = {
            "party_id": str(rec.party_id),
            "business_name": rec.business_name,
            "description": rec.description,
            "registered_at_tick": int(rec.registered_at_tick),
        }
    return out


def _business_entities_public(world: "World") -> list[dict]:
    from realm.economy.businesses import BusinessEntity

    out: list[dict] = []
    for biz in world.businesses.values():
        if not isinstance(biz, BusinessEntity):
            continue
        out.append(
            {
                "business_id": biz.business_id,
                "owner_party": str(biz.owner_party),
                "business_name": biz.business_name,
                "business_type_tag": biz.business_type_tag,
                "status": biz.status,
                "registered_plot_ids": [str(p) for p in biz.registered_plot_ids],
            }
        )
    out.sort(key=lambda r: r["business_id"])
    return out


def _nascent_settlements_public(world: "World") -> list[dict]:
    from realm.population.nascent_settlements import NascentSettlement

    out: list[dict] = []
    for ns in world.nascent_settlements.values():
        if not isinstance(ns, NascentSettlement):
            continue
        out.append(
            {
                "nascent_id": ns.nascent_id,
                "island_id": ns.island_id,
                "anchor_plot_id": str(ns.anchor_plot_id),
                "member_plot_ids": [str(p) for p in ns.member_plot_ids],
                "resident_count": ns.resident_count,
                "consecutive_game_days": ns.consecutive_game_days,
            }
        )
    out.sort(key=lambda r: r["nascent_id"])
    return out


def _chemistry_catalog_public() -> dict[str, int]:
    from realm.science.chemistry import ELEMENT_SYMBOLS, REACTIONS_PUBLIC

    return {"element_count": len(ELEMENT_SYMBOLS), "reaction_count": len(REACTIONS_PUBLIC)}


def _intel_listings_public(world: "World") -> list[dict]:
    """Public view of active intelligence-market listings (grades hidden)."""
    out: list[dict] = []
    for row in world.intel_listings:
        if str(row.get("status", "")) != "active":
            continue
        rid = str(row.get("report_id", ""))
        report = world.survey_reports.get(rid)
        if report is None:
            continue
        out.append(
            {
                "listing_id": str(row.get("listing_id", "")),
                "seller": str(row.get("seller", "")),
                "report_id": rid,
                "plot_id": str(report.plot_id),
                "survey_type": report.survey_type,
                "is_deep": report.is_deep,
                "conducted_at_tick": int(report.conducted_at_tick),
                "ask_price_cents": int(row.get("ask_price_cents", 0)),
                "listed_at_tick": int(row.get("listed_at_tick", 0)),
            }
        )
    return out


def _player_owned_reports_public(world: "World", party: PartyId) -> list[dict]:
    """Public view of reports owned by ``party`` (grades revealed)."""
    out: list[dict] = []
    for report in world.visible_survey_reports_for(party):
        out.append(
            {
                "report_id": report.report_id,
                "plot_id": str(report.plot_id),
                "conducted_by": str(report.conducted_by),
                "conducted_at_tick": int(report.conducted_at_tick),
                "survey_type": report.survey_type,
                "is_deep": report.is_deep,
                "grades": dict(report.grades),
            }
        )
    return out


def _forward_contracts_public(world: "World", party: PartyId) -> list[dict]:
    """Forward contracts involving ``party`` as buyer or seller."""
    out: list[dict] = []
    for c in world.contracts:
        if str(c.get("kind", "")) != "forward_contract":
            continue
        if str(c.get("seller", "")) != str(party) and str(c.get("buyer", "")) != str(party):
            continue
        out.append(dict(c))
    return out


def world_summary_dict(world: "World", party: PartyId) -> dict[str, Any]:
    """Sprint 6 — Phase D.4: ultra-lightweight HUD payload.

    Intended for high-frequency polling (every ~30 ticks). Excludes the plots
    grid, full inventories, and event-log bodies — just enough for the HUD
    bar at the top of the UI.
    """
    cash_acct = str(party_cash_account(party))
    balances = world.ledger.snapshot()
    cash_cents = int(balances.get(cash_acct, 0))
    try:
        from realm.economy.pricing import _FAIR_VALUE_CENTS
    except Exception:
        _FAIR_VALUE_CENTS = {}  # type: ignore[assignment]
    inv_value_cents = 0
    for mat, qty in world.inventory.stock_for_party(party).items():
        unit = int(_FAIR_VALUE_CENTS.get(str(mat), 0))
        inv_value_cents += unit * int(qty)
    building_value = sum(
        int(pb.book_value_cents)
        for pb in world.placed_buildings.values()
        if str(pb.built_by) == str(party)
    )
    net_worth_estimate = cash_cents + inv_value_cents + building_value

    active = [
        {
            "run_id": a.run_id,
            "plot_id": str(a.plot_id),
            "recipe_id": a.recipe_id,
            "ticks_remaining": int(a.ticks_remaining),
            "runs_remaining": int(getattr(a, "runs_remaining", 0)),
        }
        for a in world.active_production
        if a.party == party
    ]

    maintenance_warning: list[dict[str, Any]] = []
    try:
        from realm.maintenance import building_efficiency_pct
        for b in world.plot_buildings:
            if b.get("party") != str(party):
                continue
            iid = str(b.get("instance_id") or "")
            if not iid:
                continue
            pct = building_efficiency_pct(world, iid)
            if pct < 100:
                maintenance_warning.append({
                    "instance_id": iid,
                    "building_id": str(b.get("building_id") or ""),
                    "plot_id": str(b.get("plot_id") or ""),
                    "efficiency_pct": int(pct),
                })
    except Exception:
        pass

    npc_msgs = world.scenario_state.get("npc_messages", []) if isinstance(world.scenario_state, dict) else []
    unread_msgs = sum(1 for m in npc_msgs if not bool(m.get("read")))
    unread_feed = len(getattr(world, "world_feed_log", []) or [])

    open_orders = sum(
        1
        for lst in world.market_asks_by_material.values()
        for o in lst
        if o.party == party
    ) + sum(
        1
        for lst in world.market_bids_by_material.values()
        for o in lst
        if o.party == party
    )

    ac_count = 0
    try:
        for c in getattr(world, "contracts", []) or []:
            if str(c.get("status") or "") != "active":
                continue
            ps = str(party)
            if (
                c.get("buyer") == ps
                or c.get("seller") == ps
                or c.get("borrower") == ps
                or c.get("lender") == ps
                or c.get("from_party") == ps
                or c.get("to_party") == ps
            ):
                ac_count += 1
    except Exception:
        ac_count = 0

    active_job_openings = sum(
        1 for op in getattr(world, "job_openings", []) or [] if getattr(op, "filled_by", None) is None
    )
    employed_laborers = sum(
        1 for lab in getattr(world, "laborers", {}).values() if lab.employer is not None
    )

    return {
        "tick": world.tick,
        "party": str(party),
        "cash": cash_cents,
        "inventory_value_estimate": inv_value_cents,
        "building_book_value_cents": building_value,
        "net_worth_estimate": net_worth_estimate,
        "active_production": active,
        "maintenance_warnings": maintenance_warning[:8],
        "unread_npc_messages": unread_msgs,
        "unread_feed_entries": unread_feed,
        "active_contracts": int(ac_count),
        "open_orders": int(open_orders),
        "active_job_openings": int(active_job_openings),
        "employed_laborers": int(employed_laborers),
    }


def world_static_dict(world: "World") -> dict[str, Any]:
    """Read-once tables that never change during a tick loop.

    Fetched once at boot, again only after ``/dev/reset`` or a save load.
    Includes: recipes, building/hire/chemistry catalogs, scenario id,
    seed, ticks_per_game_day, FREE_MARKET_HISTORY_TICKS, the grid size
    + map_layout for the map renderer, the public party-display names
    map, and the bank plot id."""
    from realm.actions import hire_catalog_public
    from realm.core.time_scale import (
        REAL_SECONDS_PER_GAME_DAY,
        REAL_SECONDS_PER_TICK_AT_1X,
        SPEED_MULTIPLIERS,
        TICKS_PER_GAME_DAY,
        TICKS_PER_REAL_SECOND_AT_1X,
    )
    from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS
    from realm.economy.intel import FREE_MARKET_HISTORY_TICKS
    from realm.production.buildings import building_catalog_public

    scen = world.scenario_state if isinstance(world.scenario_state, dict) else {}
    map_layout = scen.get("map_layout")
    grid_w = scen.get("grid_width")
    grid_h = scen.get("grid_height")

    if grid_w is None or grid_h is None:
        max_x = -1
        max_y = -1
        for p in world.plots.values():
            if p.x > max_x:
                max_x = p.x
            if p.y > max_y:
                max_y = p.y
        if max_x >= 0 and max_y >= 0:
            grid_w = max_x + 1
            grid_h = max_y + 1

    return {
        "seed": world.seed,
        "scenario_id": world.scenario_id,
        "world_name": world.world_name,
        "ticks_per_game_day": TICKS_PER_GAME_DAY,
        # Wall-clock pacing canon (Law 2 / doc 09). Solo / public mode shards
        # both observe these; only the host-loop ``speed`` multiplier varies.
        "real_seconds_per_game_day": REAL_SECONDS_PER_GAME_DAY,
        "real_seconds_per_tick_at_1x": REAL_SECONDS_PER_TICK_AT_1X,
        "ticks_per_real_second_at_1x": TICKS_PER_REAL_SECOND_AT_1X,
        "sim_speed_presets": list(SPEED_MULTIPLIERS),
        "market_history_free_window_ticks": FREE_MARKET_HISTORY_TICKS,
        "map_layout": map_layout,
        "grid_width": int(grid_w) if grid_w is not None else None,
        "grid_height": int(grid_h) if grid_h is not None else None,
        "uniform_plots": _grid_is_uniform(world),
        "recipes": recipe_public_list(),
        "building_catalog": building_catalog_public(),
        "hire_catalog": hire_catalog_public(),
        "chemistry_catalog": _chemistry_catalog_public(),
        "party_display_names": dict(world.party_display_names),
        "bank_plot_id": scen.get("bank_plot"),
        "parties": [str(x) for x in world.parties],
        "player_starting_cash_cents": PLAYER_STARTING_CASH_CENTS,
        "regional_advantages": {str(k): dict(v) for k, v in world.regional_advantages.items()},
    }


def world_player_dict(world: "World", party: PartyId) -> dict[str, Any]:
    """Everything tied to one player's view that changes during play.

    Polled alongside ``/world/summary`` on the realtime tick. Includes:
    cash + sub-accounts, full inventory for the party, owned plots
    (with subsurface + recipe_ids), owned reports, player price alerts,
    in-transit shipments, forward contracts, bank rates + loans, the
    party's recipe book, the party's active production runs, and the
    party's placed buildings + maintenance status."""
    from realm.infrastructure.power_grid import compute_grid_regions
    from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
    from realm.world.world import claim_cost_cents_for_plot

    _regions = compute_grid_regions(world)
    powered_set = {
        pid
        for rid, reg in _regions.items()
        if reg.capacity_per_day > 0 and not rid.startswith("grid_iso_")
        for pid in reg.plot_ids
    }
    density_map = world.scenario_state.get("population_density") or {}

    cash_acct = str(party_cash_account(party))
    balances = world.ledger.snapshot()
    cash_cents = int(balances.get(cash_acct, 0))
    try:
        from realm.economy.pricing import _FAIR_VALUE_CENTS
    except Exception:
        _FAIR_VALUE_CENTS = {}  # type: ignore[assignment]
    inv_value_cents = 0
    for mat, qty in world.inventory.stock_for_party(party).items():
        unit = int(_FAIR_VALUE_CENTS.get(str(mat), 0))
        inv_value_cents += unit * int(qty)
    party_s = str(party)
    building_book_value_cents = sum(
        int(pb.book_value_cents)
        for pb in world.placed_buildings.values()
        if str(pb.built_by) == party_s
    )

    inventory: dict[str, Any] = {}
    for mat, raw in world.inventory.stock.get(party, {}).items():
        from realm.core.inventory import _normalize_bucket

        by_q = _normalize_bucket(raw)
        total = sum(by_q.values())
        if total <= 0:
            continue
        inventory[str(mat)] = {
            "total": total,
            "by_quality": {
                "high": int(by_q.get("high", 0)),
                "standard": int(by_q.get("standard", 0)),
                "low": int(by_q.get("low", 0)),
            },
        }

    owned_plots: list[dict[str, Any]] = []
    for p in world.plots.values():
        if p.owner is None or str(p.owner) != party_s:
            continue
        density = float(density_map.get(str(p.plot_id), 0.0))
        entry: dict[str, Any] = {
            "id": str(p.plot_id),
            "x": p.x,
            "y": p.y,
            "terrain": p.terrain.value,
            "surveyed": p.surveyed,
            "deep_surveyed": getattr(p, "deep_surveyed", False),
            "powered": str(p.plot_id) in powered_set,
            "population_density": density,
            "claim_cost_cents": claim_cost_cents_for_plot(world, p.plot_id),
        }
        if p.surveyed:
            sub_view: dict[str, float] = {
                "iron_ore_grade": p.subsurface.iron_ore_grade,
                "copper_ore_grade": p.subsurface.copper_ore_grade,
                "clay_grade": p.subsurface.clay_grade,
                "coal_grade": p.subsurface.coal_grade,
                "sulfur_grade": p.subsurface.sulfur_grade,
                "saltpeter_grade": p.subsurface.saltpeter_grade,
                "tin_grade": p.subsurface.tin_grade,
                "lead_grade": p.subsurface.lead_grade,
                "phosphate_grade": p.subsurface.phosphate_grade,
                "silica_grade": p.subsurface.silica_grade,
            }
            if getattr(p, "deep_surveyed", False):
                sub_view["platinum_grade"] = p.subsurface.platinum_grade
                sub_view["oil_shale_grade"] = p.subsurface.oil_shale_grade
                sub_view["rare_earth_grade"] = p.subsurface.rare_earth_grade
            entry["subsurface"] = sub_view
            entry["recipe_ids"] = recipe_ids_on_plot_for_owner(world, p)
        if world.use_plot_output_logistics:
            entry["output_stock"] = dict(world.plot_output_stock.get(str(p.plot_id), {}))
        from realm.production.production import (
            _count_nearby_buildings_same_owner,
            cluster_bonus_for_plot,
        )

        entry["cluster_bonus"] = cluster_bonus_for_plot(world, party, p.plot_id)
        entry["nearby_buildings_same_owner"] = _count_nearby_buildings_same_owner(
            world, party, p.plot_id
        )
        owned_plots.append(entry)

    plot_buildings = [
        {**b, "maintenance": _building_maintenance_view(world, b)}
        for b in world.plot_buildings
        if str(b.get("party") or "") == party_s
    ]

    active_production = [
        {
            "run_id": a.run_id,
            "party": str(a.party),
            "plot_id": str(a.plot_id),
            "recipe_id": a.recipe_id,
            "ticks_remaining": int(a.ticks_remaining),
            "runs_remaining": int(getattr(a, "runs_remaining", 0)),
        }
        for a in world.active_production
        if a.party == party
    ]

    in_transit = [
        {
            "id": s.shipment_id,
            "shipment_id": s.shipment_id,
            "party": str(s.party),
            "material": str(s.material),
            "qty": int(s.qty),
            "from_plot_id": str(s.from_plot_id) if s.from_plot_id else None,
            "dest_plot_id": str(s.dest_plot_id),
            "arrive_tick": int(s.arrive_tick),
        }
        for s in world.in_transit
        if s.party == party
    ]

    recipe_book = sorted(world.party_recipe_books.get(party, set()))

    price_alerts = list(world.scenario_state.get("player_price_alerts") or []) if party_s == "player" else []

    return {
        "tick": world.tick,
        "party": party_s,
        "cash_cents": cash_cents,
        "inventory_value_estimate": inv_value_cents,
        "building_book_value_cents": building_book_value_cents,
        "net_worth_estimate": cash_cents + inv_value_cents + building_book_value_cents,
        "player_accounts": _player_accounts_public(world) if party_s == "player" else [],
        "inventory": inventory,
        "owned_plots": owned_plots,
        "plot_buildings": plot_buildings,
        "active_production": active_production,
        "in_transit": in_transit,
        "forward_contracts": _forward_contracts_public(world, party),
        "owned_reports": _player_owned_reports_public(world, party),
        "price_alerts": price_alerts,
        "bank_rates": _bank_rates_public(world) if party_s == "player" else None,
        "bank_loans": _bank_loans_for_player(world) if party_s == "player" else [],
        "recipe_book": [str(x) for x in recipe_book],
    }


def world_map_dict(world: "World") -> dict[str, Any]:
    """Lean map-only view for the world renderer.

    Per-plot fields kept (cheap):
      id, x, y, terrain, owner, surveyed, deep_surveyed, powered,
      population_density

    Per-plot fields intentionally OMITTED:
      * ``claim_cost_cents`` — computed by ``claim_cost_cents_for_plot``,
        which calls the real-estate valuation graph. Doing that 76800
        times for Genesis adds ~9 seconds to the payload build. Fetched
        on demand via ``GET /plots/{id}/value`` when the player opens
        the PlotDetail panel.
      * ``subsurface`` — surveyor-private; delivered via ``/world/player``
        for plots the party owns / has reports for.
      * ``recipe_ids`` — small derivative computation that lives in the
        plot's recipe book; ``/world/player`` carries it for owned plots,
        the PlotDetail panel can refetch otherwise.

    Drops ``world_cell_to_plot`` and per-plot ``world_cells`` on uniform
    grids — derivable from ``(x, y)`` as ``p-{x}-{y}``."""
    from realm.infrastructure.power_grid import compute_grid_regions
    from realm.world.plot_scale import (
        plot_grid_side,
        plot_world_cells_tuple,
        plot_world_span,
    )

    _regions = compute_grid_regions(world)
    powered_set = {
        pid
        for rid, reg in _regions.items()
        if reg.capacity_per_day > 0 and not rid.startswith("grid_iso_")
        for pid in reg.plot_ids
    }
    density_map = world.scenario_state.get("population_density") or {}
    uniform = _grid_is_uniform(world)

    plots_out: list[dict[str, Any]] = []
    for p in world.plots.values():
        density = float(density_map.get(str(p.plot_id), 0.0))
        entry: dict[str, Any] = {
            "id": str(p.plot_id),
            "x": p.x,
            "y": p.y,
            "terrain": p.terrain.value,
            "owner": p.owner,
            "surveyed": p.surveyed,
            "powered": str(p.plot_id) in powered_set,
        }
        # Boolean / numeric defaults are omitted to keep the JSON tiny on
        # Genesis (~76800 plots, most are unsurveyed + unpowered + empty).
        if getattr(p, "deep_surveyed", False):
            entry["deep_surveyed"] = True
        if density > 0.0:
            entry["population_density"] = density
        lm_raw = (world.landmass_id or {}).get(str(p.plot_id))
        if lm_raw is not None and int(lm_raw) >= 0:
            entry["landmass_id"] = int(lm_raw)
        if not uniform:
            _, _, wt, ht = plot_world_span(p)
            gcw, gch = plot_grid_side(p)
            entry["world_tiles_w"] = wt
            entry["world_tiles_h"] = ht
            entry["grid_cells_w"] = gcw
            entry["grid_cells_h"] = gch
            entry["world_cells"] = [{"x": cx, "y": cy} for cx, cy in plot_world_cells_tuple(p)]
            entry["parcel_shape"] = getattr(p, "parcel_shape", "") or "poly"
        plots_out.append(entry)

    scen = world.scenario_state if isinstance(world.scenario_state, dict) else {}
    out: dict[str, Any] = {
        "tick": world.tick,
        "uniform_plots": uniform,
        "map_layout": scen.get("map_layout"),
        "grid_width": scen.get("grid_width"),
        "grid_height": scen.get("grid_height"),
        "plots": plots_out,
    }
    if not uniform:
        out["world_cell_to_plot"] = dict(scen.get("world_cell_to_plot") or {})
    return out


def world_feed_dict(world: "World", *, since_tick: int | None = None) -> dict[str, Any]:
    """Event log + world feed + npc message tails.

    With ``since_tick=None`` returns the last 120 events / 1500 feed
    rows / 48 npc messages (matches legacy ``/world`` behaviour).

    With ``since_tick=N`` returns only rows whose ``tick`` is strictly
    greater than ``N`` — clients track their high-water mark and only
    pull deltas, which keeps the wire small after the first load."""
    if since_tick is not None and since_tick >= 0:
        def _since(rows: list, n: int) -> list:
            return [r for r in rows if int(r.get("tick", 0)) > n]

        events = _since(list(world.event_log), since_tick)
        feed = _since(list(world.world_feed_log), since_tick)
        npc = _since(list(world.npc_messages_to_player), since_tick)
        analytics = _since(list(world.analytics_purchases), since_tick)
    else:
        events = list(world.event_log[-120:])
        feed = list(world.world_feed_log[-1500:])
        npc = list(world.npc_messages_to_player[-48:])
        analytics = list(world.analytics_purchases[-48:])

    return {
        "tick": world.tick,
        "since_tick": since_tick,
        "event_log": events,
        "world_feed_log": feed,
        "npc_messages": npc,
        "analytics_purchases": analytics,
        "intel_listings": _intel_listings_public(world),
    }


def world_compact_dict(world: "World") -> dict[str, Any]:
    """Small JSON snapshot for dev/automation: player + aggregates, no full ``plots`` grid."""
    from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
    from realm.core.time_scale import TICKS_PER_GAME_DAY

    player = PartyId("player")
    balances = {str(k): v for k, v in world.ledger.snapshot().items()}
    player_acct = str(party_cash_account(player))
    bal_sample: dict[str, int] = {player_acct: balances.get(player_acct, 0)}
    for acct, cents in sorted(
        ((k, v) for k, v in balances.items() if k != player_acct),
        key=lambda kv: -abs(kv[1]),
    )[:24]:
        bal_sample[acct] = cents

    inv_player = world.inventory.stock_for_party(player)
    inv_top = [
        {"material": str(m), "qty": q}
        for m, q in sorted(inv_player.items(), key=lambda x: -x[1])[:28]
    ]

    player_plot_entries: list[dict[str, Any]] = []
    for pid, pl in world.plots.items():
        if pl.owner != player:
            continue
        player_plot_entries.append(
            {
                "id": str(pid),
                "terrain": pl.terrain.value,
                "surveyed": pl.surveyed,
                "recipe_ids": recipe_ids_on_plot_for_owner(world, pl),
            }
        )
    player_plot_entries.sort(key=lambda x: x["id"])

    hint_mountain: str | None = None
    hint_any: str | None = None
    for pl in world.plots.values():
        if pl.owner is not None:
            continue
        pid_s = str(pl.plot_id)
        if hint_any is None:
            hint_any = pid_s
        if pl.terrain == Terrain.MOUNTAIN and hint_mountain is None:
            hint_mountain = pid_s

    settler_n = sum(1 for p in world.parties if str(p).startswith("settler_"))
    ask_mats = len(world.market_asks_by_material)
    ask_lots = sum(len(v) for v in world.market_asks_by_material.values())

    def _trim_event(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        msg = out.get("message")
        if isinstance(msg, str) and len(msg) > 220:
            out["message"] = msg[:220] + "…"
        return out

    scen = world.scenario_state
    scen_preview: dict[str, Any] = {}
    if isinstance(scen, dict):
        for k in sorted(scen.keys())[:14]:
            v = scen[k]
            if isinstance(v, (int, float, bool)) or v is None:
                scen_preview[k] = v
            else:
                s = str(v)
                scen_preview[k] = s if len(s) <= 100 else s[:100] + "…"

    return {
        "compact": True,
        "seed": world.seed,
        "tick": world.tick,
        "ticks_per_game_day": TICKS_PER_GAME_DAY,
        "scenario_id": world.scenario_id,
        "plot_counts": {
            "total": _world_map_tile_count(world),
            "deeds": len(world.plots),
            "claimed": sum(1 for pl in world.plots.values() if pl.owner is not None),
            "player_owned": len(player_plot_entries),
        },
        "claim_hint_mountain_plot_id": hint_mountain,
        "claim_hint_any_plot_id": hint_any,
        "settler_party_count": settler_n,
        "party_count": len(world.parties),
        "balances_sample_cents": bal_sample,
        "player": {
            "balance_cents": balances.get(player_acct, 0),
            "inventory_top": inv_top,
            "plots": player_plot_entries,
            "buildings": [
                {**b, "maintenance": _building_maintenance_view(world, b)}
                for b in world.plot_buildings
                if b.get("party") == str(player)
            ],
        },
        "active_production": [
            {
                "run_id": a.run_id,
                "party": str(a.party),
                "plot_id": str(a.plot_id),
                "recipe_id": a.recipe_id,
                "ticks_remaining": a.ticks_remaining,
            }
            for a in world.active_production
            if a.party == player
        ][:24],
        "in_transit": [
            {
                "shipment_id": s.shipment_id,
                "party": str(s.party),
                "material": str(s.material),
                "qty": s.qty,
                "dest_plot_id": str(s.dest_plot_id),
                "arrive_tick": s.arrive_tick,
            }
            for s in world.in_transit
            if s.party == player
        ][:16],
        "market_asks_summary": {"materials_with_asks": ask_mats, "total_lots": ask_lots},
        "event_log_tail": [_trim_event(e) for e in world.event_log[-36:]],
        "world_feed_tail": [_trim_event(e) for e in world.world_feed_log[-48:]],
        "npc_messages_tail": list(world.npc_messages_to_player[-12:]),
        "scenario_state_preview": scen_preview,
    }

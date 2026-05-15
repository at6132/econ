"""Phase 10B — dynamic shipping routes (no NPC bootstrap lanes, traffic, uncharted)."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.genesis.shippers import NPC_SHIPPER_IDS, _try_traffic_route_discovery
from realm.infrastructure.movement import (
    UNCHARTED_TIME_MULTIPLIER,
    dispatch_shipment,
    deliver_transit,
)
from realm.infrastructure.route_operators import find_cheapest_operator, register_route
from realm.actions import claim_plot
from realm.world import bootstrap_genesis
from realm.world.geo import manhattan
from realm.world.regions import all_region_ids, region_for_plot, route_key


def test_no_npc_shipper_routes_at_bootstrap() -> None:
    w = bootstrap_genesis(seed=11, settler_count=8, grid_width=24, grid_height=18)
    n = 0
    for _k, entries in (w.scenario_state.get("route_operators") or {}).items():
        for e in entries:
            if str(e.get("operator_party")) in {str(s) for s in NPC_SHIPPER_IDS}:
                n += 1
    assert n == 0


def test_uncharted_takes_2x_time_for_inter_island() -> None:
    w = bootstrap_genesis(seed=22, settler_count=6, grid_width=24, grid_height=18, map_layout="islands")
    w.scenario_state["route_operators"] = {}
    player = PartyId("player")
    plots_by_island: dict[int, list[PlotId]] = {}
    for pid, p in w.plots.items():
        iid = (w.scenario_state.get("plot_islands") or {}).get(str(pid))
        if iid is None:
            continue
        if p.owner is not None:
            continue
        plots_by_island.setdefault(int(iid), []).append(pid)
    ids = sorted(plots_by_island.keys())
    assert len(ids) >= 2
    a = plots_by_island[ids[0]][0]
    b = plots_by_island[ids[1]][0]
    assert claim_plot(w, player, a)["ok"]
    assert claim_plot(w, player, b)["ok"]
    w.next_building_instance_seq += 1
    w.plot_buildings.append(
        {
            "instance_id": "bdock-a",
            "condition_bps": 10_000,
            "plot_id": str(a),
            "party": str(player),
            "building_id": "dock",
            "label": "d",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    w.next_building_instance_seq += 1
    w.plot_buildings.append(
        {
            "instance_id": "bdock-b",
            "condition_bps": 10_000,
            "plot_id": str(b),
            "party": str(player),
            "building_id": "dock",
            "label": "d",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    w.inventory.add(player, MaterialId("coal"), 50)
    w.inventory.add(player, MaterialId("vessel"), 1)
    w.inventory.add(player, MaterialId("grain"), 10)
    dist = manhattan(w, a, b)
    r_no = dispatch_shipment(w, player, MaterialId("grain"), 1, a, b)
    assert r_no.get("ok"), r_no
    transit_no = int(r_no["arrive_tick"]) - int(w.tick)
    ra = region_for_plot(w, a)
    rb = region_for_plot(w, b)
    assert ra and rb
    rk = route_key(ra, rb)
    reg = register_route(w, player, a, ra, rb, 3)
    assert reg.get("ok"), reg
    r_yes = dispatch_shipment(w, player, MaterialId("grain"), 1, a, b)
    assert r_yes.get("ok"), r_yes
    transit_yes = int(r_yes["arrive_tick"]) - int(w.tick)
    assert transit_no >= int(transit_yes * UNCHARTED_TIME_MULTIPLIER) - 2


def test_voyage_history_increments_on_deliver() -> None:
    w = bootstrap_genesis(seed=33, settler_count=4, grid_width=24, grid_height=18)
    player = PartyId("player")
    from realm.world.regions import region_for_coords, _world_bounds

    ww, hh = _world_bounds(w)
    plots_by_region: dict[str, list[PlotId]] = {}
    for pid in w.plots:
        p = w.plots[pid]
        r = region_for_coords(p.x, p.y, ww, hh)
        plots_by_region.setdefault(r, []).append(pid)
    regs = [r for r, ps in plots_by_region.items() if len(ps) >= 2]
    assert len(regs) >= 2
    p1 = next(pid for pid in plots_by_region[regs[0]] if w.plots[pid].owner is None)
    p2 = next(pid for pid in plots_by_region[regs[1]] if w.plots[pid].owner is None)
    assert claim_plot(w, player, p1)["ok"]
    assert claim_plot(w, player, p2)["ok"]
    w.inventory.add(player, MaterialId("grain"), 5)
    r = dispatch_shipment(w, player, MaterialId("grain"), 1, p1, p2)
    assert r.get("ok"), r
    ra = region_for_plot(w, p1)
    rb = region_for_plot(w, p2)
    assert ra and rb
    rk = route_key(ra, rb)
    arrive = int(r["arrive_tick"])
    w.tick = arrive
    deliver_transit(w)
    assert w.voyage_history.get(rk, 0) >= 1


def test_npc_registers_after_3_voyages() -> None:
    w = bootstrap_genesis(seed=44, settler_count=10, grid_width=24, grid_height=18)
    shipper = NPC_SHIPPER_IDS[0]
    if shipper not in w.parties:
        return
    home = None
    for row in w.plot_buildings:
        if str(row.get("party")) == str(shipper) and str(row.get("building_id")) == "dock":
            home = region_for_plot(w, PlotId(str(row["plot_id"])))
            break
    assert home is not None
    other = next(r for r in all_region_ids() if r != home)
    rk = route_key(home, other)
    w.scenario_state["route_operators"] = {}
    d = int(w.tick) // 1440
    w.scenario_state["route_voyage_by_day"] = {
        str(d): {rk: 1},
        str(d - 1): {rk: 1},
        str(d - 2): {rk: 1},
    }
    assert find_cheapest_operator(w, rk) is None
    _try_traffic_route_discovery(w, shipper)
    assert find_cheapest_operator(w, rk) is not None


def test_route_discovery_feed_entry() -> None:
    w = bootstrap_genesis(seed=55, settler_count=10, grid_width=24, grid_height=18)
    shipper = NPC_SHIPPER_IDS[1]
    if shipper not in w.parties:
        return
    home = None
    for row in w.plot_buildings:
        if str(row.get("party")) == str(shipper) and str(row.get("building_id")) == "dock":
            home = region_for_plot(w, PlotId(str(row["plot_id"])))
            break
    assert home is not None
    other = next(r for r in all_region_ids() if r != home)
    rk = route_key(home, other)
    w.scenario_state["route_operators"] = {}
    d = int(w.tick) // 1440
    w.scenario_state["route_voyage_by_day"] = {
        str(d): {rk: 1},
        str(d - 1): {rk: 1},
        str(d - 2): {rk: 1},
    }
    before = len(w.world_feed_log)
    _try_traffic_route_discovery(w, shipper)
    new_feed = w.world_feed_log[before:]
    assert any("shipping lane" in str(x.get("message", "")).lower() for x in new_feed)


def test_small_vessel_blocked_on_continent_route() -> None:
    w = bootstrap_genesis(seed=66, settler_count=4, grid_width=24, grid_height=18, map_layout="islands")
    player = PartyId("player")
    plots_by_island: dict[int, list[PlotId]] = {}
    for pid, p in w.plots.items():
        iid = (w.scenario_state.get("plot_islands") or {}).get(str(pid))
        if iid is None:
            continue
        if p.owner is not None:
            continue
        plots_by_island.setdefault(int(iid), []).append(pid)
    ids = sorted(plots_by_island.keys())
    assert len(ids) >= 2
    a = plots_by_island[ids[0]][0]
    b = plots_by_island[ids[1]][0]
    assert claim_plot(w, player, a)["ok"]
    assert claim_plot(w, player, b)["ok"]
    for pid in (a, b):
        w.landmass_id[str(pid)] = 0
    w.landmass_type[0] = "continent"
    w.plot_buildings[:] = [
        x
        for x in w.plot_buildings
        if str(x.get("plot_id")) not in {str(a), str(b)}
    ]
    w.next_building_instance_seq += 1
    w.plot_buildings.append(
        {
            "instance_id": "bx1",
            "condition_bps": 10_000,
            "plot_id": str(a),
            "party": str(player),
            "building_id": "dock",
            "label": "d",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    w.next_building_instance_seq += 1
    w.plot_buildings.append(
        {
            "instance_id": "bx2",
            "condition_bps": 10_000,
            "plot_id": str(b),
            "party": str(player),
            "building_id": "dock",
            "label": "d",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    w.inventory.add(player, MaterialId("coal"), 50)
    w.inventory.add(player, MaterialId("small_vessel"), 1)
    w.inventory.add(player, MaterialId("grain"), 5)
    r = dispatch_shipment(w, player, MaterialId("grain"), 1, a, b)
    assert r.get("ok") is False
    assert "vessel" in str(r.get("reason", "")).lower()

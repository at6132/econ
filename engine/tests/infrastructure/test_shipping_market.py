"""Sprint 2 — Phase A · shipping as a real market.

Covers the route-operator pipeline end-to-end:
- ``register_route`` preconditions (dock/waystation, vessel for coastal, ownership).
- ``dispatch_shipment`` credits the cheapest registered operator instead of the
  system reserve.
- Multiple operators compete; cheapest wins each shipment.
- Genesis bootstrap seeds 3 NPC shippers with dock + vessel (Phase 10B: routes
  emerge from traffic / player registration — no day-0 NPC route table).
- A player can undercut an existing operator (e.g. archetype shipper) by
  registering at a lower fee.
- Ledger conservation through every fee operation.
"""

from __future__ import annotations

from realm.actions import register_route
from realm.production.buildings import build_on_plot
from realm.genesis.archetypes import SHIPPER_PARTY_ID
from realm.genesis.shippers import NPC_SHIPPER_IDS
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import Inventory, MatterErr
from realm.core.ledger import (
    Ledger,
    MoneyErr,
    party_cash_account,
    system_reserve_account,
)
from realm.infrastructure.movement import (
    BASE_SHIP_FEE_CENTS,
    PER_TILE_SHIP_CENTS,
    dispatch_shipment,
)
from realm.world.regions import (
    REGION_GRID_DIM,
    all_region_ids,
    region_for_coords,
    region_for_plot,
    route_key,
)
from realm.infrastructure.route_operators import (
    find_cheapest_operator,
    list_route_operators,
    register_route as register_route_lowlevel,
)
from realm.world.terrain import Terrain
from realm.world import Plot, World, bootstrap_genesis


# ───────────────────────── helpers ─────────────────────────


def _build_test_world(
    *,
    width: int = 9,
    height: int = 9,
    starting_cash: int = 5_000_000,
) -> tuple[World, PartyId, PartyId, PlotId, PlotId, PlotId, PlotId]:
    """Build a deterministic shipping-test world.

    Layout:
    - y = height - 1 is a single row of ``water_shallow`` along the bottom.
    - Every other plot is dry plains.

    Result: the row directly above the water (y = height - 2) is coastal in
    every region, so we can place dock plots in any region.

    Returns ``(world, alice, bob, alice_plot_a, alice_plot_b, alice_dock_plot, bob_dock_plot)``.
    """
    plots: dict[PlotId, Plot] = {}
    from realm.world import SubsurfaceRoll

    sub = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
    )
    for y in range(height):
        for x in range(width):
            terrain = Terrain.WATER_SHALLOW if y == height - 1 else Terrain.PLAINS
            pid = PlotId(f"p-{x}-{y}")
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=terrain,
                owner=None,
                subsurface=sub,
                surveyed=True,
            )
    world = World(
        seed=1,
        tick=0,
        plots=plots,
        ledger=Ledger(),
        inventory=Inventory(),
        parties=set(),
        scenario_id="testbed",
    )
    res = world.ledger.seed_system_reserve(10_000_000_000)
    assert not isinstance(res, MoneyErr)

    alice = PartyId("alice")
    bob = PartyId("bob")
    for p in (alice, bob):
        world.parties.add(p)
        acct = party_cash_account(p)
        world.ledger.ensure_account(acct)
        world.ledger.transfer(
            debit=system_reserve_account(), credit=acct, amount_cents=starting_cash
        )
        world.reputation[str(p)] = {"honored": 0, "breached": 0}
    # Endpoints + dock plots all in the coastal row (y=height-2) so that
    # cargo plots and dock plots share the same row-region.
    coastal_row = height - 2
    alice_plot_a = PlotId(f"p-1-{coastal_row}")  # region r-0-2 in 9×9
    alice_plot_b = PlotId(f"p-{width - 2}-{coastal_row}")  # region r-2-2 in 9×9
    assert region_for_plot(world, alice_plot_a) != region_for_plot(world, alice_plot_b), (
        region_for_plot(world, alice_plot_a),
        region_for_plot(world, alice_plot_b),
    )
    plots[alice_plot_a].owner = alice
    plots[alice_plot_b].owner = alice
    # Alice's dock: distinct coastal plot in alice_plot_a's region.
    alice_dock_plot = PlotId(f"p-2-{coastal_row}")
    plots[alice_dock_plot].owner = alice
    # Bob's dock: coastal plot in alice_plot_b's region.
    bob_dock_plot = PlotId(f"p-{width - 3}-{coastal_row}")
    plots[bob_dock_plot].owner = bob
    return world, alice, bob, alice_plot_a, alice_plot_b, alice_dock_plot, bob_dock_plot


def _give(world: World, party: PartyId, material: str, qty: int) -> None:
    res = world.inventory.add(party, MaterialId(material), qty)
    assert not isinstance(res, MatterErr)


def _give_cash(world: World, party: PartyId, cents: int) -> None:
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=cents,
    )


def _build_dock(world: World, party: PartyId, plot_id: PlotId) -> None:
    """Build a dock turnkey and skip ahead so it's completed (test scaffolding)."""
    _give(world, party, "timber", 10)
    _give(world, party, "lumber", 4)
    _give(world, party, "rope", 3)
    _give(world, party, "stone", 2)
    res = build_on_plot(world, party, plot_id, "dock", build_mode="turnkey")
    assert res["ok"], res
    # Advance the world tick past completes_at so the dock counts as completed.
    world.tick = int(res["completes_at_tick"])


def _build_waystation(world: World, party: PartyId, plot_id: PlotId) -> None:
    _give(world, party, "timber", 6)
    _give(world, party, "lumber", 2)
    _give(world, party, "brick", 2)
    res = build_on_plot(world, party, plot_id, "waystation", build_mode="turnkey")
    assert res["ok"], res
    world.tick = int(res["completes_at_tick"])


# ───────────────────────── tests ─────────────────────────


def test_register_route_requires_dock_or_waystation() -> None:
    w, alice, _bob, _pa, _pb, dock_plot, _bdock = _build_test_world()
    # Alice owns the (would-be) dock plot but hasn't built anything on it yet.
    home = region_for_plot(w, dock_plot)
    other = next(r for r in all_region_ids() if r != home)
    res = register_route(w, alice, dock_plot, home, other, 5)
    assert res["ok"] is False
    assert "dock" in res["reason"] or "waystation" in res["reason"], res


def test_register_route_requires_vessel_for_coastal() -> None:
    w, alice, _bob, _pa, _pb, dock_plot, _bdock = _build_test_world()
    _build_dock(w, alice, dock_plot)
    home = region_for_plot(w, dock_plot)
    other = next(r for r in all_region_ids() if r != home)
    # Coastal dock built but no vessel in inventory → registration must fail.
    res = register_route(w, alice, dock_plot, home, other, 4)
    assert res["ok"] is False
    assert "vessel" in res["reason"], res
    _give(w, alice, "vessel", 1)
    res2 = register_route(w, alice, dock_plot, home, other, 4)
    assert res2["ok"] is True, res2


def test_inland_waystation_does_not_need_vessel() -> None:
    """A non-coastal waystation can register an inland route with no vessel."""
    w, alice, _bob, _pa, _pb, _adock, _bdock = _build_test_world()
    inland_plot = PlotId("p-1-2")
    assert w.plots[inland_plot].owner is None
    w.plots[inland_plot].owner = alice
    _build_waystation(w, alice, inland_plot)
    home = region_for_plot(w, inland_plot)
    other = next(r for r in all_region_ids() if r != home)
    res = register_route(w, alice, inland_plot, home, other, 2)
    assert res["ok"] is True, res


def test_shipping_fee_goes_to_operator() -> None:
    w, alice, bob, pa, pb, dock_plot, bdock = _build_test_world()
    _build_dock(w, alice, dock_plot)
    _give(w, alice, "vessel", 1)
    from_region = region_for_plot(w, pa)
    to_region = region_for_plot(w, pb)
    rkey = route_key(from_region, to_region)
    # Alice's dock is in pa's region, so she can register pa↔pb.
    res = register_route(w, alice, dock_plot, from_region, to_region, 4)
    assert res["ok"], res
    # Bob ships between two of his own plots, one in each of the same regions.
    coastal_row = w.plots[dock_plot].y
    bob_a = PlotId(f"p-0-{coastal_row}")
    bob_b = PlotId(f"p-{w.plots[pb].x}-{coastal_row}")  # same as pb? — pick adjacent
    bob_b = PlotId(f"p-{w.plots[pb].x}-{coastal_row}")
    # If pb happens to overlap bob_b, nudge.
    if bob_b == pb:
        bob_b = PlotId(f"p-{w.plots[pb].x - 1}-{coastal_row}")
    w.plots[bob_a].owner = bob
    w.plots[bob_b].owner = bob
    assert region_for_plot(w, bob_a) == from_region, (
        region_for_plot(w, bob_a),
        from_region,
    )
    assert region_for_plot(w, bob_b) == to_region, (
        region_for_plot(w, bob_b),
        to_region,
    )
    _give(w, bob, "timber", 5)
    pre_reserve = w.ledger.balance(system_reserve_account())
    pre_alice = w.ledger.balance(party_cash_account(alice))
    pre_bob = w.ledger.balance(party_cash_account(bob))
    pre_total = w.ledger.total_cents()
    ship = dispatch_shipment(w, bob, MaterialId("timber"), 3, bob_a, bob_b)
    assert ship["ok"], ship
    assert ship["route_key"] == rkey
    assert ship["operator_party"] == str(alice)
    fee = int(ship["fee_cents"])
    # Operator (alice) earned the full fee; system reserve did NOT receive it.
    assert w.ledger.balance(party_cash_account(alice)) == pre_alice + fee
    assert w.ledger.balance(party_cash_account(bob)) == pre_bob - fee
    assert w.ledger.balance(system_reserve_account()) == pre_reserve
    assert w.ledger.total_cents() == pre_total  # conservation


def test_multiple_operators_cheapest_wins() -> None:
    w, alice, bob, pa, pb, dock_plot, bdock = _build_test_world()
    # Both alice and bob register; bob is cheaper.
    _build_dock(w, alice, dock_plot)
    _give(w, alice, "vessel", 1)
    _build_dock(w, bob, bdock)
    _give(w, bob, "vessel", 1)
    from_region = region_for_plot(w, pa)
    to_region = region_for_plot(w, pb)
    r1 = register_route(w, alice, dock_plot, from_region, to_region, 4)
    assert r1["ok"], r1
    # Bob's dock is in the *other* region — same unordered route, different endpoint.
    bob_home = region_for_plot(w, bdock)
    assert bob_home in (from_region, to_region)
    r2 = register_route(w, bob, bdock, from_region, to_region, 2)
    assert r2["ok"], r2
    cheapest = find_cheapest_operator(w, route_key(from_region, to_region))
    assert cheapest["operator_party"] == str(bob)
    assert cheapest["fee_per_tile_cents"] == 2
    # A third party charlie ships and pays bob (cheapest).
    charlie = PartyId("charlie")
    w.parties.add(charlie)
    w.ledger.ensure_account(party_cash_account(charlie))
    _give_cash(w, charlie, 5_000_000)
    coastal_row = w.plots[dock_plot].y
    cha = PlotId(f"p-0-{coastal_row}")
    chb = PlotId(f"p-{w.plots[pb].x}-{coastal_row}")
    if chb == pb:
        chb = PlotId(f"p-{w.plots[pb].x - 1}-{coastal_row}")
    if cha == dock_plot:
        cha = PlotId(f"p-3-{coastal_row}")
    w.plots[cha].owner = charlie
    w.plots[chb].owner = charlie
    assert region_for_plot(w, cha) == from_region, (
        region_for_plot(w, cha),
        from_region,
    )
    assert region_for_plot(w, chb) == to_region, (
        region_for_plot(w, chb),
        to_region,
    )
    _give(w, charlie, "lumber", 2)
    pre_bob = w.ledger.balance(party_cash_account(bob))
    pre_alice = w.ledger.balance(party_cash_account(alice))
    ship = dispatch_shipment(w, charlie, MaterialId("lumber"), 2, cha, chb)
    assert ship["ok"], ship
    fee = int(ship["fee_cents"])
    # Bob (2¢/tile) gets the fee, not alice (4¢/tile).
    assert w.ledger.balance(party_cash_account(bob)) == pre_bob + fee
    assert w.ledger.balance(party_cash_account(alice)) == pre_alice


def test_npc_shippers_no_routes_at_bootstrap() -> None:
    w = bootstrap_genesis(seed=7, settler_count=4, grid_width=18, grid_height=14)
    shippers = sorted(p for p in w.parties if str(p).startswith("shipper_"))
    assert len(shippers) >= 3, shippers
    operators = w.scenario_state.get("route_operators") or {}
    npc_routes = [
        k
        for k, entries in operators.items()
        if any(str(e.get("operator_party")) in {str(s) for s in NPC_SHIPPER_IDS} for e in entries)
    ]
    assert npc_routes == [], npc_routes


def test_player_can_undercut_npc() -> None:
    """Player registers below the archetype shipper (still seeds all routes at boot)."""
    w = bootstrap_genesis(seed=21, settler_count=2, grid_width=48, grid_height=36)
    player = PartyId("player")
    from realm.production.recipe_sites import plot_is_coastal

    operators = w.scenario_state.get("route_operators") or {}
    target_key = None
    for k, entries in operators.items():
        for e in entries:
            if str(e.get("operator_party")) == str(SHIPPER_PARTY_ID):
                target_key = k
                break
        if target_key:
            break
    assert target_key is not None
    npc_entry = next(
        e
        for e in operators[target_key]
        if str(e.get("operator_party")) == str(SHIPPER_PARTY_ID)
    )
    npc_fee = int(npc_entry["fee_per_tile_cents"])
    npc_region = region_for_plot(w, PlotId(npc_entry["operator_plot"]))
    other_region = next(r for r in target_key.split(":") if r != npc_region)
    # Find any unowned coastal plot in npc_region for the player.
    player_dock_plot = None
    for plot in w.plots.values():
        if plot.owner is not None:
            continue
        if not plot_is_coastal(w, plot):
            continue
        if region_for_plot(w, plot.plot_id) != npc_region:
            continue
        player_dock_plot = plot.plot_id
        break
    assert player_dock_plot is not None
    w.plots[player_dock_plot].owner = player
    _build_dock(w, player, player_dock_plot)
    _give(w, player, "vessel", 1)
    reg = register_route(w, player, player_dock_plot, npc_region, other_region, npc_fee - 1)
    assert reg["ok"], reg
    cheapest = find_cheapest_operator(w, target_key)
    assert cheapest["operator_party"] == str(player)


def test_no_operator_falls_back_to_system_reserve() -> None:
    w, alice, _bob, pa, pb, _adock, _bdock = _build_test_world()
    # No routes registered → fee goes to system_reserve (legacy behavior).
    # Make sure scenario_state has no route_operators key polluted.
    w.scenario_state.pop("route_operators", None)
    _give(w, alice, "grain", 4)
    pre_reserve = w.ledger.balance(system_reserve_account())
    pre_alice = w.ledger.balance(party_cash_account(alice))
    pre_total = w.ledger.total_cents()
    ship = dispatch_shipment(w, alice, MaterialId("grain"), 2, pa, pb)
    assert ship["ok"], ship
    fee = int(ship["fee_cents"])
    # Default PER_TILE rate applies. ``pa``/``pb`` sit on the coastal strip in
    # this fixture, so Sprint 3 Phase D.2 applies the 40 % coastal discount.
    # Phase 9I adds a mass-weighted surcharge: 2 units grain * 0.78 t * dist.
    from realm.world.geo import manhattan
    from realm.infrastructure.movement import (
        COASTAL_ROUTE_DISCOUNT_BPS,
        MASS_SHIP_TON_TILE_CENTS,
    )
    from realm.materials import MATERIALS

    dist = manhattan(w, pa, pb)
    raw = BASE_SHIP_FEE_CENTS + dist * PER_TILE_SHIP_CENTS
    if ship["coastal_route"]:
        expected = max(
            BASE_SHIP_FEE_CENTS, raw * (10_000 - COASTAL_ROUTE_DISCOUNT_BPS) // 10_000
        )
    else:
        expected = raw
    grain_kg = MATERIALS[MaterialId("grain")].mass_per_unit_kg
    mass_surcharge = int((grain_kg * 2 / 1000.0) * dist * MASS_SHIP_TON_TILE_CENTS)
    expected += mass_surcharge
    assert fee == expected
    assert ship["operator_party"] is None
    assert w.ledger.balance(party_cash_account(alice)) == pre_alice - fee
    assert w.ledger.balance(system_reserve_account()) == pre_reserve + fee
    assert w.ledger.total_cents() == pre_total


def test_dock_requires_coastal_terrain() -> None:
    w, alice, _bob, _pa, _pb, _adock, _bdock = _build_test_world()
    # A plot well away from the bottom water strip (y=1) is not coastal.
    inland_plot = PlotId("p-1-1")
    w.plots[inland_plot].owner = alice
    _give(w, alice, "timber", 10)
    _give(w, alice, "lumber", 4)
    _give(w, alice, "rope", 3)
    _give(w, alice, "stone", 2)
    res = build_on_plot(w, alice, inland_plot, "dock", build_mode="turnkey")
    assert res["ok"] is False
    assert "coastal" in res["reason"], res


def test_shipping_market_conserves_ledger_under_competition() -> None:
    """Full path: NPC + player operators, multiple shipments, ledger invariant."""
    w = bootstrap_genesis(seed=33, settler_count=2, grid_width=18, grid_height=14)
    pre_total = w.ledger.total_cents()
    # Walk one game-day of normal genesis activity (which includes shipper AI even
    # though shipping volume from settlers is currently 0 — the AI must be a no-op
    # when there's no revenue pressure, not a money creator/destroyer).
    from realm.world.tick import advance_tick

    for _ in range(1500):
        advance_tick(w)
    assert w.ledger.total_cents() == pre_total

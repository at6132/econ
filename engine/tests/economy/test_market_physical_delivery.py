"""Market fills use physical delivery (DDP transit or FOB pickup), not inventory teleport."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.economy.market_delivery import DELIVERY_DDP, DELIVERY_FOB
from realm.economy.exchange import GENESIS_EXCHANGE_PARTY_ID
from realm.economy.markets import place_buy_order, place_sell_order


def _clear_exchange_asks(world, material: MaterialId) -> None:
    key = str(material)
    lst = world.market_asks_by_material.get(key, [])
    world.market_asks_by_material[key] = [
        o for o in lst if o.party != GENESIS_EXCHANGE_PARTY_ID
    ]
from realm.infrastructure.plot_logistics import plot_output_qty
from realm.production.storage_caps import party_uses_plot_storage
from realm.world import bootstrap_genesis
from realm.world.terrain import Terrain


def _ensure_cash(world, party: PartyId, cents: int) -> None:
    acc = party_cash_account(party)
    world.ledger.ensure_account(acc)
    world.ledger.transfer(debit=system_reserve_account(), credit=acc, amount_cents=cents)


def _first_forest_plot(world) -> PlotId | None:
    for pid, plot in world.plots.items():
        if plot.owner is None and plot.terrain == Terrain.FOREST:
            return pid
    return None


def test_ddp_fill_spawns_transit_not_buyer_stash() -> None:
    w = bootstrap_genesis(seed=91, grid_width=14, grid_height=12, settler_count=2)
    assert party_uses_plot_storage(w, PartyId("player"))
    seller = PartyId("player")
    buyer = PartyId("settler_001")
    _ensure_cash(w, seller, 5_000_000)
    _ensure_cash(w, buyer, 5_000_000)
    pid = _first_forest_plot(w)
    assert pid is not None
    assert claim_plot(w, seller, pid)["ok"]
    assert survey_plot(w, seller, pid).get("ok")
    buyer_pid = None
    for p_id, plot in w.plots.items():
        if plot.owner is None and plot.terrain == Terrain.PLAINS:
            buyer_pid = p_id
            break
    assert buyer_pid is not None
    assert claim_plot(w, buyer, buyer_pid)["ok"]
    w.plot_output_stock.setdefault(str(pid), {})["timber"] = 10
    before_transit = len(w.in_transit)
    before_buyer_stash = plot_output_qty(w, buyer_pid, MaterialId("timber"))
    r = place_sell_order(
        w,
        seller,
        MaterialId("timber"),
        4,
        50_000,
        from_plot_id=pid,
        delivery_terms=DELIVERY_DDP,
    )
    assert r["ok"], r
    assert plot_output_qty(w, pid, MaterialId("timber")) == 10
    _clear_exchange_asks(w, MaterialId("timber"))
    br = place_buy_order(
        w,
        buyer,
        MaterialId("timber"),
        4,
        50_001,
        delivery_plot_id=buyer_pid,
    )
    assert br.get("ok"), br
    assert len(w.in_transit) > before_transit
    assert plot_output_qty(w, buyer_pid, MaterialId("timber")) == before_buyer_stash


def test_fob_fill_creates_pickup_not_instant_stash() -> None:
    w = bootstrap_genesis(seed=92, grid_width=14, grid_height=12, settler_count=2)
    seller = PartyId("player")
    buyer = PartyId("settler_001")
    _ensure_cash(w, seller, 5_000_000)
    _ensure_cash(w, buyer, 5_000_000)
    pid = _first_forest_plot(w)
    assert pid is not None
    assert claim_plot(w, seller, pid)["ok"]
    buyer_pid = None
    for p_id, plot in w.plots.items():
        if plot.owner is None and plot.terrain == Terrain.PLAINS:
            buyer_pid = p_id
            break
    assert buyer_pid is not None
    assert claim_plot(w, buyer, buyer_pid)["ok"]
    w.plot_output_stock.setdefault(str(pid), {})["timber"] = 6
    r = place_sell_order(
        w,
        seller,
        MaterialId("timber"),
        3,
        50_000,
        from_plot_id=pid,
        delivery_terms=DELIVERY_FOB,
    )
    assert r["ok"], r
    assert plot_output_qty(w, pid, MaterialId("timber")) == 6
    _clear_exchange_asks(w, MaterialId("timber"))
    br = place_buy_order(
        w,
        buyer,
        MaterialId("timber"),
        3,
        50_001,
        delivery_plot_id=buyer_pid,
    )
    assert br.get("ok"), br
    assert len(w.market_fob_pickups) == 1
    assert w.market_fob_pickups[0].buyer == buyer
    assert plot_output_qty(w, buyer_pid, MaterialId("timber")) == 0


def test_same_plot_ddp_falls_back_to_fob_not_void() -> None:
    """When listing plot equals buyer delivery plot, settlement must not void the match."""
    from realm.economy.market_delivery import fulfill_market_matter
    from realm.economy.markets import AskOrder, BidOrder

    w = bootstrap_genesis(seed=91, grid_width=14, grid_height=12, settler_count=2)
    party = PartyId("settler_001")
    _ensure_cash(w, party, 5_000_000)
    pid = _first_forest_plot(w)
    assert pid is not None
    assert claim_plot(w, party, pid)["ok"]
    timber = MaterialId("timber")
    w.plot_output_stock.setdefault(str(pid), {})["timber"] = 8
    before_fail = sum(1 for e in w.event_log if e.get("kind") == "market_ddp_failed")
    ad = fulfill_market_matter(
        w,
        buyer=party,
        seller=party,
        material=timber,
        qty=2,
        ask=AskOrder(
            order_id="",
            party=party,
            material=timber,
            qty=0,
            price_per_unit_cents=50_000,
            from_plot_id=str(pid),
            delivery_terms=DELIVERY_DDP,
        ),
        bid=BidOrder(
            order_id="",
            party=party,
            material=timber,
            qty=0,
            max_price_per_unit_cents=50_001,
            escrow_cents=0,
            delivery_plot_id=str(pid),
        ),
    )
    from realm.core.inventory import MatterErr

    assert not isinstance(ad, MatterErr), getattr(ad, "reason", ad)
    after_fail = sum(1 for e in w.event_log if e.get("kind") == "market_ddp_failed")
    assert after_fail == before_fail

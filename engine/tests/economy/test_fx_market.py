"""Cross-currency FX orders."""

from __future__ import annotations

from realm.actions import claim_plot, register_business
from realm.core.conservation import ConservationSnapshot, assert_matter_conserved, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.economy import currencies as cur
from realm.economy import fx_market as fx
from realm.world import bootstrap_genesis


def _world_with_two_currencies() -> tuple[object, PartyId, str, str]:
    w = bootstrap_genesis(seed=1301, grid_width=48, grid_height=36, settler_count=4)
    human = PartyId("player")
    pid = next(x for x, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, human, PlotId(str(pid)))["ok"] is True
    r = register_business(
        w,
        human,
        "FX Bank",
        template_id="bank",
        registered_plot_ids=(str(pid),),
    )
    assert r["ok"] is True
    bid = str(r["business_id"])
    assert cur.create_currency(w, human, bid, "aaa", "Aaa", reserve_ratio=0.5)["ok"]
    assert cur.create_currency(w, human, bid, "bbb", "Bbb", reserve_ratio=0.5)["ok"]
    ca = f"curr_{bid}_aaa"
    cb = f"curr_{bid}_bbb"
    assert cur.mint_currency(w, human, ca, 500)["ok"]
    assert cur.mint_currency(w, human, cb, 500)["ok"]
    return w, human, ca, cb


def test_fx_order_escrows_sell_side() -> None:
    w, human, ca, _cb = _world_with_two_currencies()
    mat_a = MaterialId(w.issued_currencies[ca].material_id)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    before = w.inventory.qty(human, mat_a)
    r = fx.post_fx_order(w, human, str(mat_a), 100, "base_cents", 50)
    assert r["ok"] is True
    assert w.inventory.qty(human, mat_a) == before - 100
    assert_matter_conserved(w.inventory, snap.inventory_total_units)


def test_fx_matching_on_compatible_rates() -> None:
    w, human, ca, cb = _world_with_two_currencies()
    a = PartyId("settler_001")
    b = PartyId("settler_002")
    ma = MaterialId(w.issued_currencies[ca].material_id)
    mb = MaterialId(w.issued_currencies[cb].material_id)
    w.inventory.transfer(material=ma, qty=200, from_party=human, to_party=a)
    w.inventory.transfer(material=mb, qty=200, from_party=human, to_party=b)
    assert fx.post_fx_order(w, a, str(ma), 100, str(mb), 50)["ok"]
    assert fx.post_fx_order(w, b, str(mb), 50, str(ma), 90)["ok"]
    fx.tick_fx_matching(w)
    oa = next(o for o in w.fx_orders if o.poster == a)
    ob = next(o for o in w.fx_orders if o.poster == b)
    assert oa.status == "filled" and ob.status == "filled"


def test_fx_settlement_transfers_both_sides() -> None:
    w, human, ca, cb = _world_with_two_currencies()
    a = PartyId("settler_001")
    b = PartyId("settler_002")
    ma = MaterialId(w.issued_currencies[ca].material_id)
    mb = MaterialId(w.issued_currencies[cb].material_id)
    w.inventory.transfer(material=ma, qty=200, from_party=human, to_party=a)
    w.inventory.transfer(material=mb, qty=200, from_party=human, to_party=b)
    assert fx.post_fx_order(w, a, str(ma), 100, str(mb), 50)["ok"]
    assert fx.post_fx_order(w, b, str(mb), 50, str(ma), 90)["ok"]
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    fx.tick_fx_matching(w)
    assert w.inventory.qty(a, mb) >= 50
    assert w.inventory.qty(b, ma) >= 50
    assert_matter_conserved(w.inventory, snap.inventory_total_units)


def test_fx_order_expires_after_7_days() -> None:
    w, human, ca, _cb = _world_with_two_currencies()
    ma = MaterialId(w.issued_currencies[ca].material_id)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    r = fx.post_fx_order(w, human, str(ma), 10, "base_cents", 5)
    assert r["ok"] is True
    oid = str(r["order_id"])
    w.tick += fx.TICKS_PER_7_GAME_DAYS + 1
    fx.tick_fx_matching(w)
    o = next(x for x in w.fx_orders if x.order_id == oid)
    assert o.status == "cancelled"
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_fx_rate_board_updated_daily() -> None:
    w, human, ca, cb = _world_with_two_currencies()
    a = PartyId("settler_001")
    b = PartyId("settler_002")
    ma = MaterialId(w.issued_currencies[ca].material_id)
    mb = MaterialId(w.issued_currencies[cb].material_id)
    w.inventory.transfer(material=ma, qty=200, from_party=human, to_party=a)
    w.inventory.transfer(material=mb, qty=200, from_party=human, to_party=b)
    assert fx.post_fx_order(w, a, str(ma), 100, str(mb), 50)["ok"]
    assert fx.post_fx_order(w, b, str(mb), 50, str(ma), 90)["ok"]
    fx.tick_fx_matching(w)
    w.tick = 1440
    fx.tick_fx_rates(w)
    board = w.scenario_state.get("fx_rate_board") or {}
    assert isinstance(board, dict) and len(board) >= 1

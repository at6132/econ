"""Movement, markets, persistence, social stubs."""

from __future__ import annotations

import os
import tempfile

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.infrastructure.movement import dispatch_shipment
from realm.economy.markets import market_buy, p2p_trade, place_buy_order, place_sell_order
from realm.persistence import load_snapshot, save_snapshot
from realm.state_io import SNAPSHOT_VERSION, dump_world, dumps_json, loads_json
from realm.world.tick import advance_tick
from realm.contracts.social import honor_contract_stub, propose_contract_stub
from realm.world import bootstrap_frontier


def test_json_roundtrip_preserves_new_world_fields() -> None:
    w = bootstrap_frontier(seed=21, grid_width=2, grid_height=2)
    w.market_intel_expires_tick = 777
    w.next_building_instance_seq = 42
    w.scenario_id = "speculator"
    assert dump_world(w)["version"] == SNAPSHOT_VERSION
    blob = dumps_json(w)
    w2 = loads_json(blob)
    assert w2.market_intel_expires_tick == 777
    assert w2.next_building_instance_seq == 42
    assert w2.scenario_id == "speculator"


def test_json_roundtrip_preserves_ledger_total() -> None:
    w = bootstrap_frontier(seed=11, grid_width=3, grid_height=2)
    t0 = w.ledger.total_cents()
    blob = dumps_json(w)
    w2 = loads_json(blob)
    assert w2.ledger.total_cents() == t0
    assert w2.tick == w.tick


def test_json_roundtrip_preserves_p2p_idempotency() -> None:
    w = bootstrap_frontier(seed=96, grid_width=2, grid_height=2)
    assert p2p_trade(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        MaterialId("grain"),
        1,
        50,
        idempotency_key="snap-k",
    )["ok"] is True
    assert "snap-k" in w.p2p_idempotency
    w2 = loads_json(dumps_json(w))
    assert w2.p2p_idempotency["snap-k"]["fingerprint"] == w.p2p_idempotency["snap-k"]["fingerprint"]
    assert w2.p2p_idempotency["snap-k"]["response"].get("ok") is True


def test_json_roundtrip_preserves_market_bids() -> None:
    w = bootstrap_frontier(seed=19, grid_width=2, grid_height=2)
    consumer = PartyId("t1_consumer")
    assert place_buy_order(w, consumer, MaterialId("electricity"), 1, 40)["ok"] is True
    key = str(MaterialId("electricity"))
    row = w.market_bids_by_material[key][0]
    t0 = w.ledger.total_cents()
    w2 = loads_json(dumps_json(w))
    assert w2.ledger.total_cents() == t0
    row2 = w2.market_bids_by_material[key][0]
    assert row2.order_id == row.order_id
    assert row2.escrow_cents == row.escrow_cents
    assert row2.qty == row.qty


def test_sqlite_roundtrip() -> None:
    w = bootstrap_frontier(seed=12, grid_width=3, grid_height=2)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.sqlite")
        save_snapshot(path, w)
        w2 = load_snapshot(path)
    assert w2.seed == w.seed
    assert w2.inventory.qty(PartyId("player"), MaterialId("timber")) == w.inventory.qty(
        PartyId("player"), MaterialId("timber")
    )


def test_shipment_delivers_and_conserves_matter() -> None:
    w = bootstrap_frontier(seed=13, grid_width=4, grid_height=2)
    from realm.actions import claim_plot

    a, b = PlotId("p-0-0"), PlotId("p-1-0")
    assert claim_plot(w, PartyId("player"), a)["ok"] is True
    assert claim_plot(w, PartyId("player"), b)["ok"] is True
    u0 = w.inventory.total_units()
    assert dispatch_shipment(w, PartyId("player"), MaterialId("timber"), 2, a, b)["ok"] is True
    assert w.inventory.total_units() == u0 - 2
    for _ in range(50):
        advance_tick(w)
    assert w.inventory.qty(PartyId("player"), MaterialId("timber")) == 8


def test_p2p_trade_moves_matter_and_money() -> None:
    w = bootstrap_frontier(seed=14, grid_width=2, grid_height=2)
    seller, buyer = PartyId("player"), PartyId("t1_consumer")
    t0 = w.ledger.total_cents()
    m_buyer_before = w.inventory.qty(buyer, MaterialId("grain"))
    assert p2p_trade(w, seller, buyer, MaterialId("grain"), 1, 50)["ok"] is True
    assert w.ledger.total_cents() == t0
    assert w.inventory.qty(buyer, MaterialId("grain")) == m_buyer_before + 1


def test_market_buy_from_listed_ask() -> None:
    w = bootstrap_frontier(seed=15, grid_width=2, grid_height=2)
    buyer = PartyId("t1_consumer")
    before = w.inventory.qty(buyer, MaterialId("grain"))
    r = market_buy(w, buyer, MaterialId("grain"), 2)
    assert r["ok"] is True
    assert w.inventory.qty(buyer, MaterialId("grain")) >= before + 1


def test_build_and_hire_emit_events_and_move_cash() -> None:
    from realm.actions import claim_plot, hire_worker_stub, survey_plot
    from realm.production.buildings import build_on_plot
    from realm.core.ledger import party_cash_account

    w = bootstrap_frontier(seed=17, grid_width=3, grid_height=2)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    before = w.ledger.balance(party_cash_account(PartyId("player")))
    assert build_on_plot(w, PartyId("player"), pid, "watch_hut")["ok"] is True
    assert w.ledger.balance(party_cash_account(PartyId("player"))) == before - 15_000
    assert any(b.get("building_id") == "watch_hut" for b in w.plot_buildings)
    emp = PartyId("t1_timber_merchant")
    assert hire_worker_stub(w, PartyId("player"), emp, 1_00)["ok"] is True
    assert any(e.get("employee") == str(emp) for e in w.stub_hires)
    assert any(e.get("kind") == "build" for e in w.event_log)
    assert any(e.get("kind") == "hire" for e in w.event_log)


def test_bootstrap_default_plot_count() -> None:
    w = bootstrap_frontier(seed=0)
    assert len(w.plots) == 48 * 36


def test_market_history_after_ticks() -> None:
    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    assert len(w.market_history) >= 1
    assert "best_bids_cents" in w.market_history[0]
    advance_tick(w)
    assert len(w.market_history) >= 2
    assert w.market_history[-1]["tick"] == w.tick


def test_market_history_records_best_bid() -> None:
    w = bootstrap_frontier(seed=92, grid_width=2, grid_height=2)
    assert place_buy_order(w, PartyId("t1_consumer"), MaterialId("electricity"), 1, 144)["ok"] is True
    advance_tick(w)
    snap = w.market_history[-1]
    assert snap.get("best_bids_cents", {}).get("electricity") == 144


def test_tier1_agent_ticks_conserve_total_cents() -> None:
    w = bootstrap_frontier(seed=78, grid_width=3, grid_height=3)
    t0 = w.ledger.total_cents()
    for _ in range(60):
        advance_tick(w)
    assert w.ledger.total_cents() == t0


def test_stub_hire_recurring_wage_moves_cash() -> None:
    from realm.actions import hire_worker_stub
    from realm.core.ledger import party_cash_account

    w = bootstrap_frontier(seed=104, grid_width=2, grid_height=2)
    emp = PartyId("player")
    wkr = PartyId("t1_timber_merchant")
    wc = party_cash_account(wkr)
    w0 = w.ledger.balance(wc)
    assert hire_worker_stub(w, emp, wkr, 100, wage_per_tick_cents=7, wage_interval_ticks=1)["ok"] is True
    assert w.ledger.balance(wc) == w0 + 100
    advance_tick(w)
    advance_tick(w)
    assert w.ledger.balance(wc) >= w0 + 100 + 7


def test_contract_honor_increments_reputation() -> None:
    w = bootstrap_frontier(seed=16, grid_width=2, grid_height=2)
    pr = propose_contract_stub(w, PartyId("player"), PartyId("npc_grain_vendor"), "memo")
    cid = pr["contract_id"]
    assert honor_contract_stub(w, cid)["ok"] is True
    assert w.reputation["player"]["honored"] >= 1

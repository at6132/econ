"""Sprint 4 — Phase C tests: forward delivery contracts."""

from __future__ import annotations

from realm.contract_stubs import (
    FORWARD_DEPOSIT_BPS,
    accept_forward_contract,
    deliver_forward_contract,
    propose_forward_contract,
    tick_forward_contracts,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world import bootstrap_frontier


def _cash(w, party: str) -> int:
    return w.ledger.balance(party_cash_account(PartyId(party)))


def _give_party_inventory(w, party: PartyId, material: str, qty: int) -> None:
    ad = w.inventory.add(party, MaterialId(material), qty)
    assert not isinstance(ad, MatterErr)


def _give_party_cash(w, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=acct, amount_cents=cents
    )


def test_forward_propose_and_accept() -> None:
    w = bootstrap_frontier(seed=41, grid_width=4, grid_height=3)
    seller = PartyId("player")
    buyer = PartyId("t1_lumber_buyer")
    _give_party_cash(w, seller, 100_000)
    _give_party_cash(w, buyer, 100_000)
    starting_total = w.ledger.total_cents()
    prop = propose_forward_contract(
        w, seller, buyer, MaterialId("coal"), 50, 80, w.tick + 1000
    )
    assert prop["ok"] is True
    cid = prop["contract_id"]
    expected_deposit = (50 * 80 * FORWARD_DEPOSIT_BPS) // 10_000
    assert prop["deposit_cents"] == expected_deposit
    # Proposed status — no money has moved yet.
    seller_before = _cash(w, "player")
    acc = accept_forward_contract(w, buyer, cid)
    assert acc["ok"] is True
    # Seller's deposit was escrowed to the system reserve.
    assert _cash(w, "player") == seller_before - expected_deposit
    # Total cents still conserved (deposit just moved to reserve).
    assert w.ledger.total_cents() == starting_total
    # Contract is active.
    contract = next(c for c in w.contracts if c["id"] == cid)
    assert contract["status"] == "active"
    assert contract["deposit_cents"] == expected_deposit


def test_forward_delivery_transfers_goods_and_payment() -> None:
    w = bootstrap_frontier(seed=42, grid_width=4, grid_height=3)
    seller = PartyId("player")
    buyer = PartyId("t1_lumber_buyer")
    _give_party_cash(w, seller, 100_000)
    _give_party_cash(w, buyer, 100_000)
    seller_coal_before_giving = w.inventory.qty(seller, MaterialId("coal"))
    buyer_coal_before = w.inventory.qty(buyer, MaterialId("coal"))
    _give_party_inventory(w, seller, "coal", 50)
    starting_total = w.ledger.total_cents()
    prop = propose_forward_contract(
        w, seller, buyer, MaterialId("coal"), 50, 80, w.tick + 500
    )
    cid = prop["contract_id"]
    accept_forward_contract(w, buyer, cid)
    seller_cash_before = _cash(w, "player")
    buyer_cash_before = _cash(w, "t1_lumber_buyer")
    deposit = prop["deposit_cents"]
    payment = 50 * 80
    dr = deliver_forward_contract(w, seller, cid)
    assert dr["ok"] is True
    assert dr["payment_cents"] == payment
    assert dr["deposit_cents"] == deposit
    # Material delta: seller loses 50, buyer gains 50.
    assert w.inventory.qty(seller, MaterialId("coal")) == seller_coal_before_giving
    assert w.inventory.qty(buyer, MaterialId("coal")) == buyer_coal_before + 50
    # Cash math: buyer pays, seller receives payment + deposit back.
    assert _cash(w, "t1_lumber_buyer") == buyer_cash_before - payment
    assert _cash(w, "player") == seller_cash_before + payment + deposit
    # Conservation.
    assert w.ledger.total_cents() == starting_total
    contract = next(c for c in w.contracts if c["id"] == cid)
    assert contract["status"] == "delivered"


def test_forward_default_loses_deposit() -> None:
    w = bootstrap_frontier(seed=43, grid_width=4, grid_height=3)
    seller = PartyId("player")
    buyer = PartyId("t1_lumber_buyer")
    _give_party_cash(w, seller, 100_000)
    _give_party_cash(w, buyer, 100_000)
    prop = propose_forward_contract(
        w, seller, buyer, MaterialId("coal"), 50, 80, w.tick + 100
    )
    cid = prop["contract_id"]
    accept_forward_contract(w, buyer, cid)
    deposit = prop["deposit_cents"]
    starting_total = w.ledger.total_cents()
    buyer_cash_before = _cash(w, "t1_lumber_buyer")
    seller_cash_before = _cash(w, "player")
    # Tick past the delivery deadline.
    w.tick += 101
    tick_forward_contracts(w)
    contract = next(c for c in w.contracts if c["id"] == cid)
    assert contract["status"] == "defaulted"
    # Buyer received the escrowed deposit; seller did not regain it.
    assert _cash(w, "t1_lumber_buyer") == buyer_cash_before + deposit
    assert _cash(w, "player") == seller_cash_before
    assert w.ledger.total_cents() == starting_total
    # Seller took a reputation hit.
    seller_rep = w.reputation.get(str(seller), {})
    assert seller_rep.get("breached", 0) >= 1


def test_forward_price_locked_regardless_of_spot() -> None:
    w = bootstrap_frontier(seed=44, grid_width=4, grid_height=3)
    seller = PartyId("player")
    buyer = PartyId("t1_lumber_buyer")
    _give_party_cash(w, seller, 100_000)
    _give_party_cash(w, buyer, 100_000)
    _give_party_inventory(w, seller, "coal", 50)
    locked_price_per_unit = 80
    prop = propose_forward_contract(
        w, seller, buyer, MaterialId("coal"), 50, locked_price_per_unit, w.tick + 500
    )
    cid = prop["contract_id"]
    accept_forward_contract(w, buyer, cid)
    # Synthetic spot move: place new asks at very different price.
    from realm.markets import place_sell_order

    extra = PartyId("t1_coal_vendor")
    _give_party_inventory(w, extra, "coal", 20)
    place_sell_order(w, extra, MaterialId("coal"), 20, 1_500)  # spot way up
    # Deliver at the locked price — buyer pays 50*80, not 50*1500.
    buyer_cash_before = _cash(w, "t1_lumber_buyer")
    deliver_forward_contract(w, seller, cid)
    assert _cash(w, "t1_lumber_buyer") == buyer_cash_before - 50 * locked_price_per_unit


def test_settler_proposes_forward_with_surplus() -> None:
    """Run a few game-days; check that at least one settler eventually proposes a forward.

    Phase 7A: settler forwards now target the consolidator (Kessler Industrial)
    rather than the removed ``pop_hub_e``. The consolidator only seeds on
    coastal plots, so this test uses a grid large enough to have coastal land
    (the default ``map_layout="auto"`` will pick continent at this size and
    still produce coastal tiles via the elev<0.24 water threshold).
    """
    from realm.genesis_consolidator import CONSOLIDATOR_PARTY_ID
    from realm.genesis_forwards import tick_settler_forward_proposals
    from realm.core.ids import MaterialId
    from realm.core.inventory import MatterErr
    from realm.world import bootstrap_genesis

    w = bootstrap_genesis(seed=99, grid_width=48, grid_height=36, settler_count=6)
    assert CONSOLIDATOR_PARTY_ID in w.parties, (
        "consolidator must be seeded for settler forwards to find a buyer; "
        "increase grid size if test world lacks coastal plots"
    )
    # Stuff every settler with surplus coal so the surplus check passes.
    for p in list(w.parties):
        if not str(p).startswith("settler_"):
            continue
        ad = w.inventory.add(p, MaterialId("coal"), 100)
        assert not isinstance(ad, MatterErr)
    # Seed a spot ask so best_resting_ask_cents has a value.
    from realm.markets import place_sell_order

    seed_settler = PartyId("settler_001")
    place_sell_order(w, seed_settler, MaterialId("coal"), 1, 70)
    # Step through several day boundaries; with 10% per-day probability per
    # settler, 6 settlers × 10 days = expected ~6 proposals.
    saw = False
    for day in range(1, 15):
        w.tick = day * 1440
        tick_settler_forward_proposals(w)
        if any(
            c.get("kind") == "forward_contract" and str(c.get("seller", "")).startswith("settler_")
            for c in w.contracts
        ):
            saw = True
            break
    assert saw, "expected at least one settler-proposed forward in 15 game-days"


def test_forward_propose_invalid_inputs() -> None:
    w = bootstrap_frontier(seed=45, grid_width=4, grid_height=3)
    seller = PartyId("player")
    buyer = PartyId("t1_lumber_buyer")
    # Negative qty rejected.
    bad = propose_forward_contract(
        w, seller, buyer, MaterialId("coal"), -10, 80, w.tick + 10
    )
    assert not bad["ok"]
    # Past delivery tick rejected.
    bad2 = propose_forward_contract(
        w, seller, buyer, MaterialId("coal"), 10, 80, w.tick
    )
    assert not bad2["ok"]

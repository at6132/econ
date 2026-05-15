"""Player bank currencies: mint, redeem, reserves."""

from __future__ import annotations

from realm.actions import claim_plot, register_business
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import MoneyErr, named_reserve_account, party_cash_account
from realm.economy import currencies as cur
from realm.materials import CURRENCY_MATERIAL_IDS, PLUGIN_MATERIALS, all_material_ids
from realm.world import bootstrap_genesis


def _bank_world() -> tuple[object, PartyId, str]:
    w = bootstrap_genesis(seed=1201, grid_width=48, grid_height=36, settler_count=4)
    human = PartyId("player")
    pid = next(x for x, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, human, PlotId(str(pid)))["ok"] is True
    r = register_business(
        w,
        human,
        "Test Bank Inc",
        template_id="bank",
        registered_plot_ids=(str(pid),),
    )
    assert r.get("ok") is True
    bid = str(r["business_id"])
    return w, human, bid


def test_create_currency_registers_material() -> None:
    w, human, bid = _bank_world()
    r = cur.create_currency(w, human, bid, "tbc", "Test Bank Coin", reserve_ratio=0.2)
    assert r["ok"] is True
    mid = MaterialId(str(r["material_id"]))
    assert mid in set(all_material_ids())


def test_mint_locks_reserves() -> None:
    w, human, bid = _bank_world()
    assert cur.create_currency(w, human, bid, "xyz", "Xyz Coin", reserve_ratio=0.2)["ok"]
    cid = f"curr_{bid}_xyz"
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    r = cur.mint_currency(w, human, cid, 1000)
    assert r["ok"] is True
    assert int(r["reserve_locked"]) == 200
    ra = named_reserve_account(f"currency:{cid}")
    assert w.ledger.balance(ra) >= 200
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_mint_fails_without_sufficient_reserves() -> None:
    w, human, bid = _bank_world()
    assert cur.create_currency(w, human, bid, "low", "Low Coin", reserve_ratio=0.99)["ok"]
    cid = f"curr_{bid}_low"
    pc = party_cash_account(human)
    drain_to = PartyId("settler_002")
    bal = w.ledger.balance(pc)
    tr = w.ledger.transfer(
        debit=pc, credit=party_cash_account(drain_to), amount_cents=max(0, bal - 5)
    )
    assert not isinstance(tr, MoneyErr), tr
    r = cur.mint_currency(w, human, cid, 1_000_000)
    assert r["ok"] is False


def test_redeem_returns_reserve_proportion() -> None:
    w, human, bid = _bank_world()
    assert cur.create_currency(w, human, bid, "red", "Red Coin", reserve_ratio=0.2)["ok"]
    cid = f"curr_{bid}_red"
    assert cur.mint_currency(w, human, cid, 100)["ok"] is True
    mat = MaterialId(w.issued_currencies[cid].material_id)
    other = PartyId("settler_001")
    w.inventory.transfer(material=mat, qty=50, from_party=human, to_party=other)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    r = cur.redeem_currency(w, other, cid, 50)
    assert r["ok"] is True
    assert int(r["payout_cents"]) == 10
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_bank_suspended_when_ratio_falls_below_minimum() -> None:
    w, human, bid = _bank_world()
    assert cur.create_currency(w, human, bid, "sus", "Sus Coin", reserve_ratio=0.2)["ok"] is True
    cid = f"curr_{bid}_sus"
    assert cur.mint_currency(w, human, cid, 100)["ok"] is True
    c = w.issued_currencies[cid]
    c.reserve_cents = 1
    c.total_issued = 100
    w.tick = 1440
    cur.tick_bank_reserves(w)
    assert c.status == "suspended"


def test_fractional_reserve_multiplier() -> None:
    w, human, bid = _bank_world()
    assert cur.create_currency(w, human, bid, "mul", "Mul Coin", reserve_ratio=0.10)["ok"] is True
    cid = f"curr_{bid}_mul"
    r = cur.mint_currency(w, human, cid, 10_000)
    assert r["ok"] is True
    assert int(r["reserve_locked"]) == 1_000


def test_currency_material_is_durable() -> None:
    w, human, bid = _bank_world()
    assert cur.create_currency(w, human, bid, "dur", "Dur Coin", reserve_ratio=0.5)["ok"] is True
    mid = MaterialId("currency_dur")
    assert mid in CURRENCY_MATERIAL_IDS
    assert PLUGIN_MATERIALS[mid].durable is True

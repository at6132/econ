"""Phase 10C — business entity registration."""

from __future__ import annotations

from realm.actions.business_actions import register_business
from realm.actions.plot_actions import claim_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.world import bootstrap_genesis


def test_register_business_entity_creates_row_and_conserves_money() -> None:
    w = bootstrap_genesis(seed=55, grid_width=20, grid_height=16, settler_count=4)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, player, pid)["ok"] is True
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    before = w.ledger.balance(party_cash_account(player))
    r = register_business(
        w,
        player,
        "Test Coal LLC",
        "desc",
        template_id="coal_miner",
        registered_plot_ids=(str(pid),),
    )
    assert r["ok"] is True
    assert "business_id" in r
    assert r["business_id"] in w.businesses
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
    assert w.ledger.balance(party_cash_account(player)) == before - 1_000

"""Phase 10D — construction order + build_on_plot contractor path."""

from __future__ import annotations

from realm.actions.construction_actions import accept_construction_quote, complete_construction_job
from realm.actions.plot_actions import claim_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World, bootstrap_genesis

from plot_helpers import claimable_land_plot_id


def _give_mats(w: World, party: PartyId, spec: dict[str, int]) -> None:
    for mid, q in spec.items():
        ad = w.inventory.add(party, MaterialId(mid), int(q))
        assert not isinstance(ad, MatterErr)


def test_construction_order_completes_and_conserves() -> None:
    w = bootstrap_genesis(seed=90, grid_width=24, grid_height=18, settler_count=6)
    client = PartyId("player")
    gc = PartyId("genesis_construction")
    assert gc in w.parties
    pid = claimable_land_plot_id(w, client)
    assert claim_plot(w, client, pid)["ok"] is True
    mats = {"lumber": 8, "brick": 6, "timber": 4}
    # Contractor path deducts once in complete_construction_job and again in place_blueprint.
    for mid, qty in mats.items():
        _give_mats(w, gc, {mid: int(qty) * 2})
    cash_c = party_cash_account(client)
    w.ledger.ensure_account(cash_c)
    tr = w.ledger.transfer(
        debit=system_reserve_account(),
        credit=cash_c,
        amount_cents=500_000,
    )
    assert not isinstance(tr, MoneyErr)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    acc = accept_construction_quote(
        w,
        client,
        gc,
        pid,
        "residence",
        quoted_price_cents=200_000,
        material_responsibility="contractor",
    )
    assert acc["ok"] is True
    cid = str(acc["contract_id"])
    w.scenario_state.setdefault("plot_lease_rights", {})[str(pid)] = {
        "lessee": str(gc),
        "expires_tick": int(w.tick) + 99_999,
    }
    _give_mats(w, gc, {"coal": 10})
    done = complete_construction_job(w, gc, cid)
    assert done["ok"] is True
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
    assert any(
        str(b.get("plot_id")) == str(pid) and str(b.get("building_id")) == "residence"
        for b in w.plot_buildings
    )

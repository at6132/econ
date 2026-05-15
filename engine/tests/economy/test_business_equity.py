"""BusinessEntity registry vs live equity_stake contracts."""

from __future__ import annotations

from realm.contracts.equity_stake import accept_equity_stake, propose_equity_stake
from realm.core.ids import PartyId
from realm.economy.businesses import (
    BusinessEntity,
    business_shareholders,
    ownership_pct_bps_sold,
)
from realm.world import bootstrap_frontier


def _seed_biz(world: object) -> str:
    bid = "biz-00001"
    world.businesses[bid] = BusinessEntity(
        business_id=bid,
        owner_party=PartyId("player"),
        business_name="TestCo",
        business_type_tag="mining",
        description="t",
        registered_at_tick=0,
        registered_plot_ids=tuple(),
        sub_account_label="main",
        status="active",
        suspension_reason=None,
        public_profile=True,
        last_viability_check_tick=0,
        equity_contract_ids=[],
    )
    return bid


def test_business_shows_zero_equity_at_start() -> None:
    w = bootstrap_frontier(seed=601, grid_width=3, grid_height=3)
    bid = _seed_biz(w)
    assert ownership_pct_bps_sold(w, bid) == 0
    assert business_shareholders(w, bid) == []


def test_equity_stake_appears_in_business_shareholders() -> None:
    w = bootstrap_frontier(seed=602, grid_width=3, grid_height=3)
    bid = _seed_biz(w)
    pr = propose_equity_stake(w, PartyId("player"), PartyId("t1_consumer"), bid, 1_500, 3_000)
    cid = str(pr["contract_id"])
    assert accept_equity_stake(w, PartyId("t1_consumer"), cid)["ok"] is True
    sh = business_shareholders(w, bid)
    assert len(sh) == 1
    assert sh[0]["investor"] == "t1_consumer"
    assert sh[0]["ownership_pct_bps"] == 1_500
    assert cid in w.businesses[bid].equity_contract_ids


def test_founder_pct_decreases_after_stake_sale() -> None:
    w = bootstrap_frontier(seed=603, grid_width=3, grid_height=3)
    bid = _seed_biz(w)
    pr = propose_equity_stake(w, PartyId("player"), PartyId("t1_consumer"), bid, 2_000, 4_000)
    cid = str(pr["contract_id"])
    assert accept_equity_stake(w, PartyId("t1_consumer"), cid)["ok"] is True
    sold = ownership_pct_bps_sold(w, bid)
    assert sold == 2_000
    assert 10_000 - sold == 8_000


def test_cannot_sell_more_than_100_pct_total() -> None:
    w = bootstrap_frontier(seed=604, grid_width=3, grid_height=3)
    bid = _seed_biz(w)
    pr1 = propose_equity_stake(w, PartyId("player"), PartyId("t1_consumer"), bid, 6_000, 1_000)
    assert accept_equity_stake(w, PartyId("t1_consumer"), str(pr1["contract_id"]))["ok"] is True
    pr2 = propose_equity_stake(w, PartyId("player"), PartyId("t1_consumer"), bid, 4_500, 1_000)
    assert pr2.get("ok") is False

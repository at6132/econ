from realm.ids import PartyId
from realm.ledger import party_cash_account, system_reserve_account
from realm.world import bootstrap_frontier, generate_plots


def test_frontier_bootstrap_money_total() -> None:
    w = bootstrap_frontier(seed=7, grid_width=6, grid_height=4)
    total = w.ledger.total_cents()
    assert total == 100_000_000_000
    player = party_cash_account(PartyId("player"))
    consumer = party_cash_account(PartyId("t1_consumer"))
    lumber_buyer = party_cash_account(PartyId("t1_lumber_buyer"))
    assert w.ledger.balance(player) == 1_000_000
    assert w.ledger.balance(consumer) == 25_000
    assert w.ledger.balance(lumber_buyer) == 50_000
    assert w.ledger.balance(system_reserve_account()) == 100_000_000_000 - 1_000_000 - 25_000 - 50_000


def test_world_gen_deterministic() -> None:
    a = generate_plots(seed=99, width=3, height=3)
    b = generate_plots(seed=99, width=3, height=3)
    assert [p.terrain for p in a.values()] == [p.terrain for p in b.values()]


def test_world_public_hides_subsurface_until_surveyed() -> None:
    from realm.world import world_public_dict

    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    pub = world_public_dict(w)
    p0 = next(x for x in pub["plots"] if x["id"] == "p-0-0")
    assert "subsurface" not in p0

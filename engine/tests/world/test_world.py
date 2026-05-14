from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
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
    assert w.ledger.balance(party_cash_account(PartyId("t1_electricity_buyer"))) == 30_000
    tier2_cash = 42_000 + 55_000 + 35_000 + 38_000 + 32_000
    tier3_cash = 88_000
    assert w.ledger.balance(system_reserve_account()) == (
        100_000_000_000
        - 1_000_000
        - 25_000
        - 50_000
        - 30_000
        - tier2_cash
        - tier3_cash
    )


def test_world_gen_deterministic() -> None:
    a = generate_plots(seed=99, width=3, height=3)
    b = generate_plots(seed=99, width=3, height=3)
    assert [p.terrain for p in a.values()] == [p.terrain for p in b.values()]


def test_llm_margaux_seeded_in_bootstrap() -> None:
    w = bootstrap_frontier(seed=1, grid_width=3, grid_height=2)
    assert PartyId("llm_margaux") in w.parties
    assert "llm_margaux" in w.llm_agents
    assert w.llm_agents["llm_margaux"].get("display_name") == "Margaux Chen"


def test_world_public_hides_subsurface_until_surveyed() -> None:
    from realm.world import world_public_dict

    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    pub = world_public_dict(w)
    p0 = next(x for x in pub["plots"] if x["id"] == "p-0-0")
    assert "subsurface" not in p0


def test_world_compact_omits_full_plot_grid() -> None:
    from realm.world import world_compact_dict, world_public_dict

    w = bootstrap_frontier(seed=3, grid_width=5, grid_height=4)
    compact = world_compact_dict(w)
    assert compact.get("compact") is True
    assert "plots" not in compact
    assert compact["plot_counts"]["total"] == 5 * 4
    assert isinstance(compact.get("claim_hint_any_plot_id"), str)
    full = world_public_dict(w)
    assert len(full["plots"]) == compact["plot_counts"]["total"]

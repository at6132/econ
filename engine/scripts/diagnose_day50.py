"""Diagnose genesis economy stall — run from engine/: python scripts/diagnose_day50.py"""
from __future__ import annotations

from collections import Counter

from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.infrastructure.plot_logistics import party_material_held
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick

SEED = 42
DAYS = 30


def main() -> None:
    w = bootstrap_genesis(seed=SEED, grid_width=48, grid_height=36, settler_count=8)
    while w.tick < DAYS * TICKS_PER_GAME_DAY:
        advance_tick(w)

    print(f"=== Genesis diagnose seed={SEED} day={DAYS} ===\n")
    print(f"Tick {w.tick} — scanning events...")

    ec: Counter[str] = Counter()
    ddp_reasons: Counter[str] = Counter()
    for e in w.event_log:
        k = str(e.get("kind") or "")
        ec[k] += 1
        if k == "market_ddp_failed":
            ddp_reasons[str(e.get("reason") or "?")] += 1

    print("Top events:")
    for k, n in ec.most_common(15):
        print(f"  {k}: {n}")

    print(f"\nmarket_match total: {ec.get('market_match', 0)}")
    print(f"market_ddp_fob_fallback: {ec.get('market_ddp_fob_fallback', 0)}")
    print(f"market_fob_collected: {ec.get('market_fob_collected', 0)}")
    print(f"market_ddp_failed: {ec.get('market_ddp_failed', 0)}")
    if ddp_reasons:
        print("DDP fail reasons:")
        for r, n in ddp_reasons.most_common(10):
            print(f"  {r}: {n}")

    coal = MaterialId("coal")
    asks = w.market_asks_by_material.get("coal", [])
    bids = w.market_bids_by_material.get("coal", [])
    ask_depth = sum(o.qty + o.iceberg_hidden_qty for o in asks)
    bid_depth = sum(b.qty + b.iceberg_hidden_qty for b in bids)
    best_ask = min((o.price_per_unit_cents for o in asks), default=None)
    best_bid = max((b.max_price_per_unit_cents for b in bids), default=None)
    print(f"\nCoal book: asks={len(asks)} depth={ask_depth} best_ask={best_ask}")
    print(f"           bids={len(bids)} depth={bid_depth} best_bid={best_bid}")

    settlers = sorted(p for p in w.parties if str(p).startswith("settler_"))
    print(f"\nSettlers ({len(settlers)}) cash + coal held:")
    for p in settlers:
        cash = w.ledger.balance(party_cash_account(p))
        oids = tuple(pl.plot_id for pl in w.plots.values() if pl.owner == p)
        coal_h = party_material_held(w, p, coal, owned_plot_ids=oids)
        print(f"  {p}: cash=${cash/100:,.0f}  coal={coal_h}")

    ops = w.scenario_state.get("settler_ops_completed") or {}
    print(f"\nSettler ops total: {sum(int(v) for v in ops.values())}")
    print(f"Laborers: {len(w.laborers)}  active_production: {len(w.active_production)}")

    from realm.genesis.consolidator import CONSOLIDATOR_PARTY_ID

    if CONSOLIDATOR_PARTY_ID in w.parties:
        k = CONSOLIDATOR_PARTY_ID
        print(
            f"\nKessler: cash=${w.ledger.balance(party_cash_account(k))/100:,.0f} "
            f"coal={w.inventory.qty(k, coal)}"
        )


if __name__ == "__main__":
    main()

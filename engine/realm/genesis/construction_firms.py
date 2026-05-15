"""Phase 10D — seed a construction NPC with a real business entity + hire."""

from __future__ import annotations

from typing import Final

from realm.core.ids import PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.economy.businesses import BusinessEntity
from realm.events.event_log import log_event
from realm.world import World


GENESIS_CONSTRUCTION_PARTY_ID: Final[str] = "genesis_construction"
STARTING_CASH_CENTS: Final[int] = 350_000


def seed_genesis_construction_firm(world: World) -> None:
    """One inland firm so ``request_construction_quotes`` has a baseline bidder."""
    if world.scenario_id != "genesis":
        return
    pid = PartyId(GENESIS_CONSTRUCTION_PARTY_ID)
    if pid in world.parties:
        return
    plot_islands = world.scenario_state.get("plot_islands") or {}
    candidates: list[tuple[int, int, PlotId]] = []
    for pl in world.plots.values():
        if pl.owner is not None:
            continue
        if str(pl.terrain.value) == "ocean":
            continue
        # Leave (0,0) free for compact-grid tests that claim ``p-0-0`` for the player.
        if int(pl.x) == 0 and int(pl.y) == 0:
            continue
        candidates.append((int(pl.x), int(pl.y), pl.plot_id))
    if not candidates:
        return
    candidates.sort(key=lambda t: (t[0] + t[1], str(t[2])))
    plot_id = candidates[0][2]
    plot = world.plots.get(plot_id)
    if plot is None:
        return
    world.parties.add(pid)
    world.reputation[str(pid)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(pid)] = "Genesis Construction Co."
    acct = party_cash_account(pid)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=STARTING_CASH_CENTS,
    )
    if isinstance(tr, MoneyErr):
        world.parties.discard(pid)
        return
    plot.owner = pid
    world.next_business_seq += 1
    bid = f"biz-{world.next_business_seq:05d}"
    from realm.core.ledger import business_cash_account

    world.ledger.ensure_account(business_cash_account(bid))
    world.businesses[bid] = BusinessEntity(
        business_id=bid,
        owner_party=pid,
        business_name="Genesis Construction Co.",
        business_type_tag="construction_firm",
        description="NPC construction quotes and escrow completions.",
        registered_at_tick=int(world.tick),
        registered_plot_ids=(plot_id,),
        sub_account_label="main",
        status="active",
        suspension_reason=None,
        public_profile=True,
        last_viability_check_tick=int(world.tick),
        equity_contract_ids=[],
    )
    hired = False
    island_key = str(plot_islands.get(str(plot_id), "0"))
    for lab in world.laborers.values():
        if lab.employer is not None:
            continue
        if str(lab.island_id) != island_key and island_key != "0":
            continue
        lab.employer = pid
        lab.employment_contract = bid
        hired = True
        break
    log_event(
        world,
        "world",
        f"Seeded construction firm {pid} on {plot_id} (hired_laborer={hired}).",
    )

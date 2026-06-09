"""Genesis settler demographics — full initial cohort at boot, random arrivals up to cap, bankruptcy (matter conserved)."""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.genesis.settler_names import assign_display_name_for_new_settler
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.player_economy import GENESIS_SETTLER_STARTING_CASH_CENTS
from realm.economy.markets import cancel_all_party_resting_orders
from realm.infrastructure.plot_logistics import remove_plot_output
from realm.core.time_scale import legacy_scaled
from realm.world import World

# Default Genesis solo map: always fund this many settlers at t=0 (no random partial bootstrap).
GENESIS_DEFAULT_START_SETTLERS = 250
# After the initial cohort, ``tick_genesis_settler_lifecycle`` may spawn more until this cap (deterministic RNG).
GENESIS_DEFAULT_MAX_SETTLERS = 1000

BANKRUPT_CASH_CENTS = 12_000  # $120 — sustained distress
BANKRUPT_STREAK_TICKS = legacy_scaled(10)
SPAWN_PROB_PER_TICK = 0.00008  # ~1 arrival per 9 days — fills 42-settler gap over a year


def _gst(world: World) -> dict:
    st = world.scenario_state.setdefault("genesis", {})
    if not isinstance(st, dict):
        world.scenario_state["genesis"] = {}
        st = world.scenario_state["genesis"]
    return st


def _count_settlers(world: World) -> int:
    return sum(1 for p in world.parties if str(p).startswith("settler_"))


def _party_eligible_for_bankruptcy(party: PartyId) -> bool:
    s = str(party)
    if s in ("player", "genesis_exchange", "llm_margaux"):
        return False
    return s.startswith("settler_") or (s.startswith("llm_") and s != "llm_margaux")


def _liquidate_party_to_exchange(world: World, party: PartyId) -> None:
    """On bankruptcy, sell all inventory directly to the open market as asks."""
    from realm.economy.markets import place_sell_order
    from realm.economy.pricing import exchange_ask_cents

    # Collect all held inventory
    materials_to_sell: dict[MaterialId, int] = {}
    for mat, qty in list(world.inventory.stock_for_party(party).items()):
        if qty > 0:
            materials_to_sell[mat] = materials_to_sell.get(mat, 0) + qty
            world.inventory.remove(party, mat, qty, quality="any")

    for pid_str, bucket in list(world.plot_output_stock.items()):
        plot = world.plots.get(PlotId(pid_str))
        if plot is None or plot.owner != party:
            continue
        for ms, q in list(bucket.items()):
            qn = int(q)
            if qn <= 0:
                continue
            mid = MaterialId(ms)
            rm = remove_plot_output(world, party, PlotId(pid_str), mid, qn)
            if not isinstance(rm, MatterErr):
                materials_to_sell[mid] = materials_to_sell.get(mid, 0) + qn

    # List everything to open market at liquidation price (80% of exchange ask)
    # Use genesis_exchange as the seller party so it clears through properly
    ex = PartyId("genesis_exchange")
    for mid, qty in materials_to_sell.items():
        if qty <= 0:
            continue
        base_price = exchange_ask_cents(mid)
        liquidation_price = max(1, int(base_price * 0.80))
        world.inventory.add(ex, mid, qty)
        place_sell_order(world, ex, mid, qty, liquidation_price)

    if materials_to_sell:
        total_units = sum(materials_to_sell.values())
        log_event(
            world,
            "world_feed",
            f"{party} liquidated — {total_units} units hit the market at 80% ask price.",
            party=str(party),
        )


def _release_party_plots_and_buildings(world: World, party: PartyId) -> None:
    ps = str(party)
    for pl in world.plots.values():
        if pl.owner == party:
            pl.owner = None
    world.plot_buildings = [b for b in world.plot_buildings if b.get("party") != ps]
    world.active_production = [a for a in world.active_production if a.party != party]
    world.in_transit = [s for s in world.in_transit if s.party != party]
    world.stub_hires = [
        h for h in world.stub_hires if h.get("employer") != ps and h.get("employee") != ps
    ]
    world.contracts = [
        c
        for c in world.contracts
        if PartyId(str(c.get("supplier", ""))) != party and PartyId(str(c.get("buyer", ""))) != party
    ]


def _retire_party(world: World, party: PartyId, *, reason: str) -> None:
    if reason == "bankruptcy" and str(party).startswith("settler_"):
        from realm.agents.llm_voice import generate_settler_voice, settler_days_active

        generate_settler_voice(
            world,
            party,
            "bankruptcy",
            {
                "party_display_name": world.party_display_names.get(str(party), str(party)),
                "days_active": settler_days_active(world, party),
            },
        )
    cancel_all_party_resting_orders(world, party)
    _liquidate_party_to_exchange(world, party)
    _release_party_plots_and_buildings(world, party)
    cash = party_cash_account(party)
    bal = world.ledger.balance(cash)
    if bal > 0:
        tr = world.ledger.transfer(
            debit=cash,
            credit=system_reserve_account(),
            amount_cents=bal,
        )
        if isinstance(tr, MoneyErr):
            pass
    world.parties.discard(party)
    world.reputation.pop(str(party), None)
    world.party_display_names.pop(str(party), None)
    world.llm_agents.pop(str(party), None)
    pref = f"{party}|"
    world.market_seller_registered = {k for k in world.market_seller_registered if not k.startswith(pref)}
    st = _gst(world)
    bt = st.setdefault("broke_ticks", {})
    if isinstance(bt, dict):
        bt.pop(str(party), None)
    log_event(
        world,
        "genesis_party_retire",
        f"{party} left the economy ({reason})",
        party=str(party),
        reason=reason,
    )
    if reason == "bankruptcy":
        from realm.genesis.feed_hooks import note_genesis_bankruptcy_feed

        note_genesis_bankruptcy_feed(world, party)


def _owns_any_plot(world: World, party: PartyId) -> bool:
    return any(pl.owner == party for pl in world.plots.values())


def _tick_bankruptcies(world: World) -> None:
    st = _gst(world)
    bt = st.setdefault("broke_ticks", {})
    if not isinstance(bt, dict):
        st["broke_ticks"] = {}
        bt = st["broke_ticks"]
    for party in list(world.parties):
        if not _party_eligible_for_bankruptcy(party):
            continue
        if (
            world.scenario_id == "genesis"
            and str(party).startswith("settler_")
            and _owns_any_plot(world, party)
        ):
            bt[str(party)] = 0
            continue
        cash = party_cash_account(party)
        bal = world.ledger.balance(cash)
        key = str(party)
        if bal < BANKRUPT_CASH_CENTS:
            bt[key] = int(bt.get(key, 0)) + 1
        else:
            bt[key] = 0
        if int(bt.get(key, 0)) >= BANKRUPT_STREAK_TICKS:
            _retire_party(world, party, reason="bankruptcy")


def _format_settler_id(seq: int) -> PartyId:
    return PartyId(f"settler_{seq:03d}") if seq < 1000 else PartyId(f"settler_{seq}")


def _tick_spawns(world: World) -> None:
    st = _gst(world)
    if not st.get("settler_cycle_enabled"):
        return
    cap = int(st.get("settler_cap", 0))
    if cap <= 0:
        return
    next_seq = int(st.get("next_settler_seq", 1))
    starting_cash_cents = int(st.get("starting_settler_cents", GENESIS_SETTLER_STARTING_CASH_CENTS))
    if _count_settlers(world) >= cap:
        return
    rng = world.rng(f"genesis_settler_spawn:{world.tick}")
    if rng.random() > SPAWN_PROB_PER_TICK:
        return
    reserve = system_reserve_account()
    if world.ledger.balance(reserve) < starting_cash_cents + 50_000:
        return
    seq_try = next_seq
    sid: PartyId | None = None
    for _ in range(400):
        cand = _format_settler_id(seq_try)
        if cand not in world.parties:
            sid = cand
            break
        seq_try += 1
    if sid is None:
        return
    world.parties.add(sid)
    world.reputation[str(sid)] = {"honored": 0, "breached": 0}
    acct = party_cash_account(sid)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=reserve,
        credit=acct,
        amount_cents=starting_cash_cents,
    )
    if isinstance(tr, MoneyErr):
        world.parties.discard(sid)
        return
    assign_display_name_for_new_settler(world, sid, seq=seq_try)
    from realm.agents.settler_identity import assign_settler_personality
    from realm.world import ensure_party_recipe_book

    assign_settler_personality(world, sid)
    from realm.agents.llm_voice import record_settler_join_tick

    record_settler_join_tick(world, sid)
    ensure_party_recipe_book(world, sid)
    st["next_settler_seq"] = seq_try + 1
    log_event(
        world,
        "genesis_settler_spawn",
        f"{sid} arrived seeking opportunity (spawn seq {seq_try})",
        party=str(sid),
        seq=seq_try,
    )


def tick_genesis_settler_lifecycle(world: World) -> None:
    """Bankruptcies first, then new settler arrivals (scripted Margaux / hubs / player never auto-removed)."""
    if world.scenario_id != "genesis":
        return
    _tick_bankruptcies(world)
    _tick_spawns(world)


def genesis_settler_population_plan(
    *, settler_count: int, settler_spawn_cap: int | None = None, allow_organic_growth: bool = True
) -> tuple[int, int, bool]:
    """
    Returns ``(initial_funded_settlers, settler_cap, cycle_enabled)``.

    **Always** funds every ``settler_count`` settler at bootstrap (no random partial first wave).
    When ``settler_cap`` is greater than ``settler_count``, random spawns over time fill toward the cap.
    """
    if settler_count < 0:
        raise ValueError("settler_count must be non-negative")
    initial = settler_count
    if settler_spawn_cap is not None:
        if settler_spawn_cap < initial:
            raise ValueError("settler_spawn_cap must be >= settler_count")
        cap = settler_spawn_cap
    elif initial >= GENESIS_DEFAULT_START_SETTLERS:
        cap = GENESIS_DEFAULT_MAX_SETTLERS
    elif allow_organic_growth:
        # Small explicit count on solo-sized worlds: allow organic growth.
        cap = max(initial * 6, 50)
    else:
        cap = initial
    cycle_enabled = cap > initial
    return initial, cap, cycle_enabled

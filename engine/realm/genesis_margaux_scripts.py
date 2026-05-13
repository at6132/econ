"""Scripted Margaux lines for Genesis (no LLM) — opener + situational + auxiliary economy beats."""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.ledger import party_cash_account
from realm.markets import best_resting_ask_cents
from realm.time_scale import TICKS_PER_GAME_DAY, legacy_scaled
from realm.world import World

_MARGAUX = PartyId("llm_margaux")
_PLAYER = PartyId("player")
_HUB_E = PartyId("pop_hub_e")
_HUB_W = PartyId("pop_hub_w")

# Poll auxiliary beats (~12 windows per game-day); at most one line per poll when a trigger hits.
_AUX_POLL_TICKS = 120


def _genesis_st(world: World) -> dict[str, Any]:
    st = world.scenario_state.setdefault("genesis", {})
    if not isinstance(st, dict):
        world.scenario_state["genesis"] = {}
        st = world.scenario_state["genesis"]
    return st


def _margaux_st(world: World) -> dict[str, Any]:
    st = _genesis_st(world)
    m = st.setdefault("margaux", {})
    if not isinstance(m, dict):
        st["margaux"] = {}
        m = st["margaux"]
    return m


def _append_margaux(world: World, text: str, *, main_beat: bool = False) -> None:
    blob = world.llm_agents.get(str(_MARGAUX))
    display = str(blob.get("display_name") or "Margaux") if isinstance(blob, dict) else "Margaux"
    world.npc_messages_to_player.append(
        {
            "tick": world.tick,
            "from_party": str(_MARGAUX),
            "display_name": display,
            "text": text,
        }
    )
    if len(world.npc_messages_to_player) > 96:
        world.npc_messages_to_player = world.npc_messages_to_player[-96:]
    from realm.genesis_feed_hooks import mirror_margaux_line_to_world_feed

    mirror_margaux_line_to_world_feed(world, display, text)
    log_event(
        world,
        "npc_message",
        f"{display}: {text}",
        from_party=str(_MARGAUX),
        party=str(_MARGAUX),
    )
    if main_beat:
        _margaux_st(world)["_margaux_main_fired_this_tick"] = True


def _settler_strip_mine_count(world: World) -> int:
    return sum(
        1
        for b in world.plot_buildings
        if b.get("building_id") == "strip_mine" and str(b.get("party", "")).startswith("settler_")
    )


def _player_workshop_ids(world: World) -> set[str]:
    return {
        str(b.get("building_id", ""))
        for b in world.plot_buildings
        if b.get("party") == str(_PLAYER) and b.get("building_id")
    }


def _game_day(world: World) -> int:
    return world.tick // TICKS_PER_GAME_DAY


def _settler_party_count(world: World) -> int:
    return sum(1 for p in world.parties if str(p).startswith("settler_"))


def _total_resting_ask_rows(world: World) -> int:
    return sum(len(lst) for lst in world.market_asks_by_material.values())


def _aux_settler_coal_microspread(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_coalspread_{d}"):
        return None
    rows = sorted(
        (
            (int(o.price_per_unit_cents), str(o.party))
            for o in world.market_asks_by_material.get("coal", [])
            if str(o.party).startswith("settler_")
        ),
        key=lambda t: t[0],
    )
    if len(rows) < 2:
        return None
    if rows[1][0] - rows[0][0] > 3:
        return None
    mx[f"aux_coalspread_{d}"] = True
    return (
        f"Settler coal is stacked {rows[0][0]}¢ and {rows[1][0]}¢ — pennies apart. "
        "Whoever blinks first feeds the hubs for free. Don't be the tape under that train."
    )


def _aux_settler_coal_crowd(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_coalcrowd_{d}"):
        return None
    parties: set[str] = set()
    for o in world.market_asks_by_material.get("coal", []):
        ps = str(o.party)
        if ps.startswith("settler_"):
            parties.add(ps)
    if len(parties) < 2:
        return None
    mx[f"aux_coalcrowd_{d}"] = True
    return (
        f"{len(parties)} different settlers are sitting on coal asks at once — that's not depth, that's a knife fight "
        "in one clip. Undercut clean or walk away until the bodies clear."
    )


def _aux_player_run_margin(world: World, mx: dict[str, Any]) -> str | None:
    if world.tick % TICKS_PER_GAME_DAY != legacy_scaled(16):
        return None
    d = _game_day(world)
    cash = world.ledger.balance(party_cash_account(_PLAYER))
    prev = mx.get("_cash_margin_snap")
    mx["_cash_margin_snap"] = cash
    if mx.get(f"aux_margin_note_{d}"):
        return None
    if prev is None:
        return None
    prev_i = int(prev)
    if prev_i <= 0:
        return None
    if cash > int(prev_i * 1.25) and cash > 1_200_000:
        mx[f"aux_margin_note_{d}"] = True
        return (
            "Your cash stack grew meaningfully overnight on paper — if that's production, keep flanking the crowded clips; "
            "if it's liquidation, don't confuse runway for tailwind."
        )
    if cash < int(prev_i * 0.72) and cash < 900_000:
        mx[f"aux_margin_note_{d}"] = True
        return (
            "Cash drew down hard vs yesterday — if that's deliberate inventory buys, pace yourself; "
            "if it's leakage, cancel dead listings before the hubs notice you're thin."
        )
    return None


def _aux_settler_net_pulse(world: World, mx: dict[str, Any]) -> str | None:
    if world.tick % TICKS_PER_GAME_DAY != legacy_scaled(8):
        return None
    d = _game_day(world)
    cur = _settler_party_count(world)
    prev = mx.get("_snap_settlers_for_pulse")
    mx["_snap_settlers_for_pulse"] = cur
    if mx.get(f"aux_pop_pulse_{d}"):
        return None
    if prev is None:
        return None
    delta = cur - int(prev)
    if delta >= 18:
        mx[f"aux_pop_pulse_{d}"] = True
        return (
            f"We netted +{delta} settler filings since yesterday — desks are filling faster than kitchens. "
            "Specialize early or you'll be wage furniture."
        )
    if delta <= -10:
        mx[f"aux_pop_pulse_{d}"] = True
        return (
            f"Headcount shed {-delta} settlers in a day — that's either discipline or defaults stacking. "
            "Either way, labor queues loosen for whoever still has cash."
        )
    return None


def _aux_player_cash_pinch(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_cash_pinch_{d}"):
        return None
    cash = world.ledger.balance(party_cash_account(_PLAYER))
    if cash >= 380_000:
        return None
    if not any(str(b.get("party")) == str(_PLAYER) for b in world.plot_buildings):
        return None
    mx[f"aux_cash_pinch_{d}"] = True
    return (
        f"Your wallet just slipped under ${cash / 100:.0f} — if payroll and relists are both screaming, "
        "pause builds and turn inventory into clips before the board ghosts you."
    )


def _aux_player_float_strong(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_float_{d}"):
        return None
    cash = world.ledger.balance(party_cash_account(_PLAYER))
    if cash < 2_200_000:
        return None
    mx[f"aux_float_{d}"] = True
    return (
        "You're carrying more dry powder than most claimants — that can ride a bad streak, "
        "but idle cash is also frozen optionality. Park the rest in listings or inputs, not ego."
    )


def _aux_hub_grain_stress(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_hubgrain_{d}"):
        return None
    qe = world.inventory.qty(_HUB_E, MaterialId("grain"))
    qw = world.inventory.qty(_HUB_W, MaterialId("grain"))
    if qe + qw > 1_300:
        return None
    mx[f"aux_hubgrain_{d}"] = True
    return (
        f"Eastern hub grain {qe}u, western {qw}u — that's a thin pantry for the basket program. "
        "If you're long grain, this is when hubs pay attention."
    )


def _aux_hub_coal_draw(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_hubcoal_{d}"):
        return None
    q = world.inventory.qty(_HUB_E, MaterialId("coal"))
    if q > 300:
        return None
    mx[f"aux_hubcoal_{d}"] = True
    return (
        f"Eastern hub coal on-hand is ~{q}u — they'll keep lifting asks if someone feeds the clips. "
        "Strip operators should feel that suction."
    )


def _aux_grain_rich_pressed(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_grainpx_{d}"):
        return None
    ga = best_resting_ask_cents(world, MaterialId("grain"))
    if ga is None or ga < 132:
        return None
    mx[f"aux_grainpx_{d}"] = True
    return (
        f"Grain best ask just printed {ga}¢ — staple prices wheezing that high means somebody's hoarding or hubs are panic-buying. "
        "Watch the eastern clip first; it's usually the canary."
    )


def _aux_thin_book(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_thin_{d}"):
        return None
    n = _total_resting_ask_rows(world)
    if n > 32:
        return None
    mx[f"aux_thin_{d}"] = True
    return (
        f"Whole board only shows {n} live ask rows — thin books shake producers out faster than bankruptcy. "
        "If you're long, list small; if you're flat, keep powder for the first thick relist."
    )


def _aux_ele_stress(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_elec_{d}"):
        return None
    ea = best_resting_ask_cents(world, MaterialId("electricity"))
    if ea is None or ea < 58:
        return None
    mx[f"aux_elec_{d}"] = True
    return (
        f"Electricity lifting at {ea}¢ tells me someone upstream is taxing your patience. "
        "Lock a clip or bake slower recipes until the clearinghouse reloads."
    )


def _aux_timber_soft(world: World, mx: dict[str, Any]) -> str | None:
    d = _game_day(world)
    if mx.get(f"aux_timber_{d}"):
        return None
    ta = best_resting_ask_cents(world, MaterialId("timber"))
    prev = mx.get("_prev_timber_ask")
    mx["_prev_timber_ask"] = ta
    if prev is None or ta is None:
        return None
    prev_i = int(prev)
    if prev_i < 18 or ta >= prev_i:
        return None
    drop = (prev_i - ta) / float(prev_i)
    if drop < 0.08:
        return None
    mx[f"aux_timber_{d}"] = True
    return (
        f"Timber best ask just relaxed {prev_i}¢ → {ta}¢ — ~{int(drop * 100)}% giveback. "
        "Good for mills, rough for stump jockeys who chased the top tick."
    )


def _run_margaux_aux_beats(world: World, mx: dict[str, Any]) -> None:
    if mx.get("_margaux_main_fired_this_tick"):
        return
    if world.tick < legacy_scaled(40):
        return
    if world.tick % _AUX_POLL_TICKS != 0:
        return
    for fn in (
        _aux_settler_coal_microspread,
        _aux_settler_coal_crowd,
        _aux_player_run_margin,
        _aux_settler_net_pulse,
        _aux_player_cash_pinch,
        _aux_player_float_strong,
        _aux_hub_grain_stress,
        _aux_hub_coal_draw,
        _aux_grain_rich_pressed,
        _aux_thin_book,
        _aux_ele_stress,
        _aux_timber_soft,
    ):
        msg = fn(world, mx)
        if msg:
            _append_margaux(world, msg, main_beat=False)
            return


def tick_genesis_margaux_scripts(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    blob = world.llm_agents.get(str(_MARGAUX))
    if not isinstance(blob, dict):
        return
    mx = _margaux_st(world)
    mx["_margaux_main_fired_this_tick"] = False

    if world.tick == legacy_scaled(14) and not blob.get("genesis_opener_sent"):
        _append_margaux(
            world,
            "I see you're on the board — I run the eastern exchange rolls. "
            "Fifty names landed with deeds; most will pick one line of business and bore a hole in the same market. "
            "If your survey showed teeth (coal, ore, clay), defend that niche — flat books starve founders.",
            main_beat=True,
        )
        blob["genesis_opener_sent"] = True

    if world.tick == legacy_scaled(22) and not mx.get("herd_strip_warned"):
        n = _settler_strip_mine_count(world)
        if n >= 18:
            _append_margaux(
                world,
                f"I'm watching the filings — {n} settler strip-mines already. "
                "If everyone ships the same clip, the book goes flat and nobody eats. "
                "Differentiate or you'll be begging for bids.",
                main_beat=True,
            )
            mx["herd_strip_warned"] = True

    seen_raw = mx.get("player_workshops_seen", [])
    seen: set[str] = set(seen_raw) if isinstance(seen_raw, list) else set()
    cur = _player_workshop_ids(world)
    new_types = cur - seen
    if new_types:
        bid = sorted(new_types)[0]
        if bid == "strip_mine":
            _append_margaux(
                world,
                "You broke ground on a strip-mine — good if your subsurface earned it. "
                "Post tight clips; the hubs are hungry but they won't chase fantasy prices.",
                main_beat=True,
            )
        elif bid in ("timber_yard", "grain_row"):
            _append_margaux(
                world,
                "Smart — primary food and fiber still clear when half the grid is chasing coal tickets.",
                main_beat=True,
            )
        elif bid == "foundry":
            _append_margaux(
                world,
                "Foundry online — you're climbing the chain. Lock ore and power before the book squeaks.",
                main_beat=True,
            )
        else:
            _append_margaux(
                world,
                f"You stood up a {bid.replace('_', ' ')} — variety is how this colony stops cosplaying one mine.",
                main_beat=True,
            )
        mx["player_workshops_seen"] = sorted(cur)

    period = legacy_scaled(120)
    if world.tick >= legacy_scaled(60) and world.tick % period == 0:
        key = f"flat_book_{world.tick // period}"
        if not mx.get(key):
            ca = best_resting_ask_cents(world, MaterialId("coal"))
            has_strip = any(
                b.get("party") == str(_PLAYER) and b.get("building_id") == "strip_mine"
                for b in world.plot_buildings
            )
            if has_strip and ca is None:
                _append_margaux(
                    world,
                    "Coal asks just went dark on the board — that's not 'sold out', that's air. "
                    "Either relist under the hubs or pivot inputs before your piles suffocate in escrow.",
                    main_beat=True,
                )
                mx[key] = True

    _run_margaux_aux_beats(world, mx)

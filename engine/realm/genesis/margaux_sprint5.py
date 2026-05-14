"""Sprint 5 — Phase E: Margaux's day 2-7 sustained arc + archetype observations.

Extends the Genesis Margaux script (``genesis_margaux_scripts``) with:

* A daily-updated **player profile** that tracks buildings, dominant
  vertical, net worth history, and contract activity.
* 12 auxiliary beats keyed to days 2-7 + player profile conditions.
* Archetype observation beats fired when a specific Tier-2 archetype
  intersects the player's economic position.

All beats fire **at most once** (tracked in
``world.scenario_state["margaux_beats_fired"]``). Beats are queued via
``world.npc_messages_to_player`` exactly like the existing Margaux script;
nothing pushes or interrupts the player.
"""

from __future__ import annotations

from typing import Any

from realm.events.event_log import log_event
from realm.genesis.archetypes import (
    FLIPPER_PARTY_ID,
    SHIPPER_PARTY_ID,
)
from realm.genesis.consolidator import CONSOLIDATOR_PARTY_ID
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.world import World


__all__ = [
    "update_margaux_player_profile",
    "tick_margaux_sprint5_beats",
    "fire_archetype_observation_beat",
    "MARGAUX_BEATS_FIRED_KEY",
]


_MARGAUX = PartyId("llm_margaux")
_PLAYER = PartyId("player")
_TICKS_PER_GAME_DAY = 1440
MARGAUX_BEATS_FIRED_KEY = "margaux_beats_fired"


# ───────────────────────── player profile ─────────────────────────


def _profile(world: World) -> dict[str, Any]:
    p = world.scenario_state.setdefault(
        "margaux_player_profile",
        {
            "buildings_built": [],
            "dominant_vertical": None,
            "days_in_dominant_vertical": 0,
            "net_worth_history": [],
            "archetypes_encountered": [],
            "contracts_won": 0,
            "tenders_bid": 0,
            "loans_taken": 0,
            "last_profile_day": -1,
        },
    )
    if not isinstance(p, dict):
        world.scenario_state["margaux_player_profile"] = {
            "buildings_built": [],
            "dominant_vertical": None,
            "days_in_dominant_vertical": 0,
            "net_worth_history": [],
            "archetypes_encountered": [],
            "contracts_won": 0,
            "tenders_bid": 0,
            "loans_taken": 0,
            "last_profile_day": -1,
        }
        p = world.scenario_state["margaux_player_profile"]
    return p


def _beats_fired(world: World) -> set[str]:
    raw = world.scenario_state.setdefault(MARGAUX_BEATS_FIRED_KEY, [])
    if isinstance(raw, set):
        return raw
    s = set(str(x) for x in raw) if isinstance(raw, (list, tuple)) else set()
    world.scenario_state[MARGAUX_BEATS_FIRED_KEY] = list(s)
    return s


def _record_beat_fired(world: World, beat_id: str) -> None:
    raw = world.scenario_state.setdefault(MARGAUX_BEATS_FIRED_KEY, [])
    if isinstance(raw, list):
        if beat_id not in raw:
            raw.append(beat_id)
    else:
        world.scenario_state[MARGAUX_BEATS_FIRED_KEY] = [beat_id]


def _player_net_worth_cents(world: World) -> int:
    cash = world.ledger.balance(party_cash_account(_PLAYER))
    inv = world.inventory.snapshot().get(_PLAYER, {}) or {}
    # Conservatively count inventory at zero — Margaux's beats are net-worth
    # heuristic, not portfolio valuation. Cash is the dominant signal early.
    _ = inv
    return int(cash)


def _player_buildings(world: World) -> list[str]:
    return [
        str(b.get("building_id", ""))
        for b in world.plot_buildings
        if b.get("party") == str(_PLAYER)
    ]


def _player_dominant_vertical(world: World) -> str | None:
    """Approximate vertical by counting the most numerous building line."""
    counts: dict[str, int] = {}
    for bid in _player_buildings(world):
        if not bid:
            continue
        counts[bid] = counts.get(bid, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def update_margaux_player_profile(world: World) -> None:
    """Snapshot the player's economic state once per game-day."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    p = _profile(world)
    day = int(world.tick) // _TICKS_PER_GAME_DAY
    if int(p.get("last_profile_day", -1)) >= day:
        return
    p["buildings_built"] = _player_buildings(world)
    prev_vertical = p.get("dominant_vertical")
    cur_vertical = _player_dominant_vertical(world)
    p["dominant_vertical"] = cur_vertical
    if cur_vertical is not None and cur_vertical == prev_vertical:
        p["days_in_dominant_vertical"] = int(p.get("days_in_dominant_vertical", 0)) + 1
    elif cur_vertical is not None:
        p["days_in_dominant_vertical"] = 1
    else:
        p["days_in_dominant_vertical"] = 0
    history = list(p.get("net_worth_history") or [])
    history.append(_player_net_worth_cents(world))
    if len(history) > 30:
        history = history[-30:]
    p["net_worth_history"] = history
    # Count contracts the player won (status active/repaid/delivered as winner).
    contracts_won = 0
    loans_taken = 0
    for c in world.contracts:
        if str(c.get("borrower", "")) == str(_PLAYER) and c.get("kind") == "bank_loan":
            loans_taken += 1
        if c.get("kind") == "forward_contract":
            if c.get("status") in ("active", "delivered"):
                if str(c.get("buyer", "")) == str(_PLAYER) or str(
                    c.get("seller", "")
                ) == str(_PLAYER):
                    contracts_won += 1
    p["contracts_won"] = contracts_won
    p["loans_taken"] = loans_taken
    # Tender bids: scan tenders if available.
    tenders_bid = 0
    for t in world.scenario_state.get("tenders", []) or []:
        if not isinstance(t, dict):
            continue
        for bid in t.get("bids", []) or []:
            if str(bid.get("party", "")) == str(_PLAYER):
                tenders_bid += 1
                break
    p["tenders_bid"] = tenders_bid
    p["last_profile_day"] = day


def _append_margaux(world: World, text: str) -> None:
    blob = world.llm_agents.get(str(_MARGAUX))
    display = (
        str(blob.get("display_name") or "Margaux") if isinstance(blob, dict) else "Margaux"
    )
    world.npc_messages_to_player.append(
        {
            "tick": int(world.tick),
            "from_party": str(_MARGAUX),
            "display_name": display,
            "text": text,
        }
    )
    if len(world.npc_messages_to_player) > 96:
        world.npc_messages_to_player = world.npc_messages_to_player[-96:]
    from realm.genesis.feed_hooks import mirror_margaux_line_to_world_feed

    mirror_margaux_line_to_world_feed(world, display, text)
    log_event(
        world,
        "npc_message",
        f"{display}: {text}",
        from_party=str(_MARGAUX),
        party=str(_MARGAUX),
    )


def _fire_once(world: World, beat_id: str, text: str) -> bool:
    fired = _beats_fired(world)
    if beat_id in fired:
        return False
    _append_margaux(world, text)
    _record_beat_fired(world, beat_id)
    return True


# ───────────────────────── beats ─────────────────────────


def _net_worth_declined(p: dict) -> bool:
    history = p.get("net_worth_history") or []
    return len(history) >= 2 and history[-1] < history[-2]


def _kessler_has_vertical_share(world: World, vertical: str | None) -> bool:
    """Heuristic: did Kessler trade > 40% of recent matches in this vertical?"""
    if not vertical:
        return False
    cutoff = int(world.tick) - 7 * _TICKS_PER_GAME_DAY
    totals = 0
    kessler = 0
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < cutoff:
            break
        if ev.get("kind") != "market_match":
            continue
        mat = str(ev.get("material", ""))
        if mat != vertical:
            continue
        try:
            qty = int(ev.get("qty", 0))
        except (TypeError, ValueError):
            continue
        totals += qty
        if str(ev.get("seller", "")) == str(CONSOLIDATOR_PARTY_ID):
            kessler += qty
    if totals < 10:
        return False
    return (kessler * 100) // max(1, totals) >= 40


def tick_margaux_sprint5_beats(world: World) -> None:
    """Day-gated Sprint 5 beats. Each fires once; call once per tick.

    Cheap to call every tick: the day gate is the first thing checked.
    """
    if world.scenario_id != "genesis":
        return
    if str(_MARGAUX) not in world.llm_agents:
        return
    day = int(world.tick) // _TICKS_PER_GAME_DAY
    if day < 2 or day > 7:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    p = _profile(world)
    vertical = p.get("dominant_vertical")

    # Day 2
    if day == 2:
        if _net_worth_declined(p):
            _fire_once(
                world,
                "day2_net_worth_decline",
                (
                    "Your first day wasn't clean — most aren't. The question is whether "
                    "your cost basis is going down or your revenue is going up. Check both."
                ),
            )
        if _kessler_has_vertical_share(world, vertical):
            _fire_once(
                world,
                "day2_kessler_same_pool",
                (
                    "I see you and Kessler are fishing the same pool. "
                    "Kessler has $80K to play with. What's your move?"
                ),
            )

    # Day 3
    if day == 3:
        if int(p.get("tenders_bid", 0)) == 0:
            _fire_once(
                world,
                "day3_no_tenders",
                (
                    "The hubs post what they need. Some people wait to be invited. "
                    "The ones who last usually aren't waiting."
                ),
            )
        if int(p.get("loans_taken", 0)) >= 1:
            _fire_once(
                world,
                "day3_loan_taken",
                (
                    "Borrowed money makes everything move faster. It also makes "
                    "everything hurt faster. The clock is real now."
                ),
            )

    # Day 4
    if day == 4:
        if int(p.get("days_in_dominant_vertical", 0)) >= 3:
            _fire_once(
                world,
                "day4_comfortable_vertical",
                (
                    "You've been running the same operation for 3 days. Either you're "
                    "building reserves or you're comfortable. Comfortable is expensive "
                    "in a moving market."
                ),
            )
        if any(b in ("dock", "waystation") for b in p.get("buildings_built") or []):
            _fire_once(
                world,
                "day4_logistics_player",
                (
                    "You're in the logistics game now. The margins are thin but the "
                    "volume is endless. Compound them."
                ),
            )

    # Day 5
    if day == 5:
        if _kessler_has_vertical_share(world, vertical):
            _fire_once(
                world,
                "day5_kessler_share",
                (
                    f"Kessler owns 40% of your market. That number is going up. "
                    f"The inputs they're buying today are the ceiling they're "
                    f"building for you tomorrow."
                ),
            )
        if int(p.get("contracts_won", 0)) >= 1:
            _fire_once(
                world,
                "day5_contract_secured",
                (
                    "Contract secured. Now you have a commitment instead of a hope. "
                    "That's worth something — don't miss the delivery."
                ),
            )

    # Day 6
    if day == 6:
        if len(p.get("buildings_built") or []) >= 3:
            _fire_once(
                world,
                "day6_small_empire",
                (
                    "Three operations. You're running a small empire. The hard part "
                    "about empires is that they need maintenance — all of them, all "
                    "the time."
                ),
            )

    # Day 7
    if day == 7:
        nw = (p.get("net_worth_history") or [0])[-1]
        if nw > 2_000_000:
            _fire_once(
                world,
                "day7_week_one_strong",
                (
                    "Week one. You're still here and you have assets. Most people "
                    "who try this fold in the first few days."
                ),
            )
        elif nw < 500_000:
            _fire_once(
                world,
                "day7_week_one_thin",
                (
                    "Week one and you're thin. That's not necessarily bad — it means "
                    "you built things. The question is whether what you built will "
                    "pay back."
                ),
            )


# ───────────────────────── archetype observations ─────────────────────────


def _player_owns_plot_adjacent_to(world: World, plot_id_str: str) -> bool:
    target = world.plots.get(plot_id_str)
    if target is None:
        # plot_id_str may not be a valid PlotId here; tolerate the lookup.
        return False
    target_xy = (int(target.x), int(target.y))
    for plot in world.plots.values():
        if plot.owner != _PLAYER:
            continue
        dx = abs(int(plot.x) - target_xy[0])
        dy = abs(int(plot.y) - target_xy[1])
        if (dx + dy) == 1:
            return True
    return False


def fire_archetype_observation_beat(world: World, *, archetype: str, **kwargs: Any) -> None:
    """Optional hook called from archetype tick paths after key events.

    ``archetype`` ∈ {"flipper_listed", "consolidator_acquired", "shipper_raised_fee"}.
    """
    if world.scenario_id != "genesis":
        return
    if str(_MARGAUX) not in world.llm_agents:
        return
    if archetype == "flipper_listed":
        report_id = str(kwargs.get("report_id", ""))
        plot_id = str(kwargs.get("plot_id", ""))
        if not plot_id:
            return
        if not _player_owns_plot_adjacent_to(world, plot_id):
            return
        beat_id = f"obs_flipper_adj_{report_id}"
        _fire_once(
            world,
            beat_id,
            (
                "Prospect Holdings is selling intel on land near yours. "
                "Worth a look, or a preemptive claim."
            ),
        )
    elif archetype == "consolidator_acquired":
        material = str(kwargs.get("material", ""))
        if not material:
            return
        beat_id = f"obs_kessler_{material}_day{int(world.tick) // _TICKS_PER_GAME_DAY}"
        _fire_once(
            world,
            beat_id,
            (
                f"Kessler just moved heavy on {material}. You're downstream of that. "
                "Plan accordingly."
            ),
        )
    elif archetype == "shipper_raised_fee":
        route_key_s = str(kwargs.get("route_key", ""))
        beat_id = f"obs_cross_country_{route_key_s}_day{int(world.tick) // _TICKS_PER_GAME_DAY}"
        _fire_once(
            world,
            beat_id,
            (
                "Cross-Country just raised their fee. That comes out of your margin. "
                "Own the route or pay the toll."
            ),
        )

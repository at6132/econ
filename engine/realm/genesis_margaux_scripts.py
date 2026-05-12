"""Scripted Margaux lines for Genesis (no LLM) — opener + situational triggers."""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.markets import best_resting_ask_cents
from realm.world import World

_MARGAUX = PartyId("llm_margaux")
_PLAYER = PartyId("player")


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


def _append_margaux(world: World, text: str) -> None:
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
    log_event(
        world,
        "npc_message",
        f"{display}: {text}",
        from_party=str(_MARGAUX),
        party=str(_MARGAUX),
    )


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


def tick_genesis_margaux_scripts(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    blob = world.llm_agents.get(str(_MARGAUX))
    if not isinstance(blob, dict):
        return
    mx = _margaux_st(world)

    if world.tick == 14 and not blob.get("genesis_opener_sent"):
        _append_margaux(
            world,
            "I see you're on the board — I run the eastern exchange rolls. "
            "Fifty names landed with deeds; most will pick one line of business and bore a hole in the same market. "
            "If your survey showed teeth (coal, ore, clay), defend that niche — flat books starve founders.",
        )
        blob["genesis_opener_sent"] = True

    if world.tick == 22 and not mx.get("herd_strip_warned"):
        n = _settler_strip_mine_count(world)
        if n >= 18:
            _append_margaux(
                world,
                f"I'm watching the filings — {n} settler strip-mines already. "
                "If everyone ships the same clip, the book goes flat and nobody eats. "
                "Differentiate or you'll be begging for bids.",
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
            )
        elif bid in ("timber_yard", "grain_row"):
            _append_margaux(
                world,
                "Smart — primary food and fiber still clear when half the grid is chasing coal tickets.",
            )
        elif bid == "foundry":
            _append_margaux(
                world,
                "Foundry online — you're climbing the chain. Lock ore and power before the book squeaks.",
            )
        else:
            _append_margaux(
                world,
                f"You stood up a {bid.replace('_', ' ')} — variety is how this colony stops cosplaying one mine.",
            )
        mx["player_workshops_seen"] = sorted(cur)

    if world.tick >= 60 and world.tick % 120 == 0:
        key = f"flat_book_{world.tick // 120}"
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
                )
                mx[key] = True

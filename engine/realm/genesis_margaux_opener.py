"""Scripted Margaux opener for Genesis — runs without LLM (texture + hook for later Tier-3 opinions)."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId
from realm.world import World

_MARGAUX = PartyId("llm_margaux")


def tick_genesis_margaux_script_opener(world: World) -> None:
    if world.scenario_id != "genesis" or world.tick != 14:
        return
    blob = world.llm_agents.get(str(_MARGAUX))
    if not isinstance(blob, dict) or blob.get("genesis_opener_sent"):
        return
    display = str(blob.get("display_name") or "Margaux")
    text = (
        "I see you're on the board — I run the eastern exchange rolls. "
        "Fifty names landed with deeds; most will pick one line of business and bore a hole in the same market. "
        "If your survey showed teeth (coal, ore, clay), defend that niche — flat books starve founders."
    )
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
    blob["genesis_opener_sent"] = True
    log_event(
        world,
        "npc_message",
        f"{display}: {text}",
        from_party=str(_MARGAUX),
        party=str(_MARGAUX),
    )

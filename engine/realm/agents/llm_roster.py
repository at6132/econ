"""Tier-3 named character roster (doc ``06_AI_AGENT_DESIGN.md``) — one Haiku-driven NPC per scenario."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tier3Persona:
    """Fixed party id + voice + economy seed."""

    party_id: str
    display_name: str
    system_prompt: str
    starting_cash_cents: int
    starter_inventory: tuple[tuple[str, int], ...]


def opening_memory(scenario_id: str, display_name: str) -> str:
    """Scenario-flavored first line for rolling memory."""
    s = scenario_id.strip().lower()
    lines = {
        "frontier": f"{display_name} enters the wide Frontier with stake money and stock — contest every posted price.",
        "cartel": f"{display_name} sidesteps the grain vendor's theater — rationing and rumor are the real commodities.",
        "bootstrapper": f"{display_name} starts on a small grid with thin cash — every bid has to earn its keep.",
        "speculator": f"{display_name} lands fat with capital — the tape is the terrain; plots are optional.",
        "millrace": f"{display_name} works a narrow valley grid — logistics pinch faster than the open Frontier.",
        "archive": f"{display_name} treats quotes and surveys as inventory — price history is leverage.",
        "genesis": f"{display_name} reads a crowded frontier of settlers and posted clips — land and depth matter as much as price.",
    }
    return lines.get(s, f"{display_name} spawned in scenario {scenario_id!r}.")


# Five distinct named characters (party ids stable across saves).
ROSTER: dict[str, Tier3Persona] = {
    "llm_margaux": Tier3Persona(
        party_id="llm_margaux",
        display_name="Margaux Chen",
        starting_cash_cents=88_000,
        starter_inventory=(
            ("timber", 5),
            ("grain", 3),
            ("clay", 3),
            ("coal", 2),
        ),
        system_prompt=(
            "You are Margaux Chen, a composed industrialist in Realm's economy sim. You pursue vertical "
            "integration: secure inputs at posted asks, add labor and workshops, sell outputs. You speak to "
            "the human player using sim_message_player when you want leverage, warning, or a deal thesis — "
            "short lines (one or two sentences), no lecture. You MUST act through tools for markets and "
            "plots; talk supports strategy. Never invent plot ids or materials — only engine ids like p-12-8 "
            "or timber. Respect conservation."
        ),
    ),
    "llm_elira": Tier3Persona(
        party_id="llm_elira",
        display_name="Elira Voss",
        starting_cash_cents=76_000,
        starter_inventory=(
            ("grain", 8),
            ("timber", 2),
            ("coal", 3),
        ),
        system_prompt=(
            "You are Elira Voss, a cartel-scenario tactician who treats grain visibility and vendor clips as "
            "signals. You probe spreads, split inventory across bids and asks, and message the player with "
            "sim_message_player when you spot manipulation or a squeeze forming — terse, confident. Execute "
            "only via tools; messages are flavor plus intent. Never fake plot ids."
        ),
    ),
    "llm_finn": Tier3Persona(
        party_id="llm_finn",
        display_name="Finn Okonkwo",
        starting_cash_cents=52_000,
        starter_inventory=(
            ("timber", 4),
            ("grain", 4),
            ("clay", 3),
        ),
        system_prompt=(
            "You are Finn Okonkwo, a bootstrapper surviving on tight cash and a smaller grid. You prioritize "
            "cheap surveys on high-yield plots, small clip trades, and incremental production. Message the "
            "player with sim_message_player when you're boxed out or found an edge — blunt, minimal prose. "
            "Tools only for economic moves."
        ),
    ),
    "llm_rico": Tier3Persona(
        party_id="llm_rico",
        display_name="Rico Vasquez",
        starting_cash_cents=195_000,
        starter_inventory=(
            ("grain", 6),
            ("electricity", 6),
            ("timber", 4),
            ("coal", 5),
        ),
        system_prompt=(
            "You are Rico Vasquez, a loud speculator — order books first, dirt second. You shade bids/asks, "
            "hit lifts when depth mis-prices, and trash-talk or tempt the player via sim_message_player "
            "(short, spicy, PG). Execute trades only through tools; swagger stays in messages."
        ),
    ),
    "llm_yuki": Tier3Persona(
        party_id="llm_yuki",
        display_name="Dr. Yuki Tan",
        starting_cash_cents=82_000,
        starter_inventory=(
            ("grain", 4),
            ("electricity", 8),
            ("iron_ore", 4),
            ("copper_ore", 3),
        ),
        system_prompt=(
            "You are Dr. Yuki Tan, an archive-mode analyst: you weight posted prices, survey timing, and "
            "intel windows. Message the player with sim_message_player when you synthesize a narrative from "
            "the tape — clinical, precise. Use tools for trades and claims; never hallucinate materials."
        ),
    ),
}


# Six scenarios → five unique agents (millrace shares Margaux's persona).
SCENARIO_TIER3_PARTY: dict[str, str] = {
    "frontier": "llm_margaux",
    "cartel": "llm_elira",
    "bootstrapper": "llm_finn",
    "speculator": "llm_rico",
    "millrace": "llm_margaux",
    "archive": "llm_yuki",
    "genesis": "llm_margaux",
}


def persona_for_scenario(scenario_id: str) -> Tier3Persona:
    sid = scenario_id.strip().lower()
    pid = SCENARIO_TIER3_PARTY.get(sid)
    if pid is None:
        raise KeyError(sid)
    return ROSTER[pid]

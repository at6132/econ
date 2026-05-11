"""Tier 3 — LLM-driven named agents (doc ``06_AI_AGENT_DESIGN.md``).

Uses Haiku + tools from ``realm.llm_haiku`` when ``ANTHROPIC_API_KEY`` is set; otherwise
``tick_tier3_llm_agents`` is a no-op so CI stays deterministic.

Cooldown between planning windows: ``REALM_LLM_COOLDOWN_TICKS`` (default ``24`` ticks).
"""

from __future__ import annotations

import json
import os
from typing import Any

from realm.actions import claim_plot, start_production_on_plot, survey_plot
from realm.event_log import log_event
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account
from realm.llm_haiku import run_haiku_tool_session, session_cap_micro_usd
from realm.markets import market_buy, place_buy_order, place_sell_order
from realm.materials import MATERIALS
from realm.movement import dispatch_shipment
from realm.world import World


def _cooldown_ticks() -> int:
    try:
        return max(1, int(os.environ.get("REALM_LLM_COOLDOWN_TICKS", "24")))
    except ValueError:
        return 24


def _coerce_int(x: Any, default: int = 0) -> int:
    if isinstance(x, bool):
        return default
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x)
    try:
        return int(str(x).strip())
    except ValueError:
        return default


def _material_id(raw: Any) -> MaterialId | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    mid = MaterialId(s)
    if mid not in MATERIALS:
        return None
    return mid


def build_observation_json(world: World, party: PartyId) -> str:
    """Compact JSON observation for the model (no hidden subsurface on unowned unsurveyed)."""
    cash = world.ledger.balance(party_cash_account(party))
    inv = {str(m): q for m, q in world.inventory.stock_for_party(party).items() if q > 0}
    plots_out: list[dict[str, Any]] = []
    for p in world.plots.values():
        if p.owner != party:
            continue
        row: dict[str, Any] = {
            "id": str(p.plot_id),
            "x": p.x,
            "y": p.y,
            "terrain": p.terrain.value,
            "surveyed": p.surveyed,
        }
        if p.surveyed:
            row["subsurface"] = {
                "iron_ore_grade": p.subsurface.iron_ore_grade,
                "copper_ore_grade": p.subsurface.copper_ore_grade,
                "clay_grade": p.subsurface.clay_grade,
                "coal_grade": p.subsurface.coal_grade,
            }
        plots_out.append(row)
    payload = {
        "party": str(party),
        "tick": world.tick,
        "scenario_id": world.scenario_id,
        "cash_cents": cash,
        "inventory": inv,
        "owned_plots": plots_out,
        "instruction": (
            "Choose tools to advance your economic position. "
            "Use only plot ids that exist in the world grid (p-x-y). "
            "Materials must be from the catalog keys in your inventory or common market ids."
        ),
        "your_recent_messages_to_player": [
            row
            for row in world.npc_messages_to_player[-14:]
            if row.get("from_party") == str(party)
        ],
    }
    return json.dumps(payload, indent=2)


def execute_llm_tool(world: World, party: PartyId, name: str, inp: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one tool; always returns a JSON-serializable dict."""
    if name == "sim_noop":
        return {"ok": True, "action": "noop"}

    if name == "sim_message_player":
        raw = inp.get("message")
        text = str(raw).strip() if raw is not None else ""
        if not text:
            return {"ok": False, "reason": "empty message"}
        if len(text) > 420:
            text = text[:420]
        blob = world.llm_agents.get(str(party))
        display = str(blob.get("display_name") or party) if blob else str(party)
        row = {
            "tick": world.tick,
            "from_party": str(party),
            "display_name": display,
            "text": text,
        }
        world.npc_messages_to_player.append(row)
        if len(world.npc_messages_to_player) > 96:
            world.npc_messages_to_player = world.npc_messages_to_player[-96:]
        log_event(
            world,
            "npc_message",
            f"{display}: {text}",
            party=str(party),
            from_party=str(party),
        )
        return {"ok": True, "delivered": True, "length": len(text)}

    if name == "sim_place_buy_order":
        mid = _material_id(inp.get("material"))
        if mid is None:
            return {"ok": False, "reason": "unknown material"}
        qty = _coerce_int(inp.get("qty"), 0)
        px = _coerce_int(inp.get("max_price_per_unit_cents"), 0)
        return dict(place_buy_order(world, party, mid, qty, px))

    if name == "sim_place_sell_order":
        mid = _material_id(inp.get("material"))
        if mid is None:
            return {"ok": False, "reason": "unknown material"}
        qty = _coerce_int(inp.get("qty"), 0)
        px = _coerce_int(inp.get("price_per_unit_cents"), 0)
        return dict(place_sell_order(world, party, mid, qty, px))

    if name == "sim_market_buy":
        mid = _material_id(inp.get("material"))
        if mid is None:
            return {"ok": False, "reason": "unknown material"}
        max_qty = _coerce_int(inp.get("max_qty"), 0)
        return dict(market_buy(world, party, mid, max_qty))

    if name == "sim_claim_plot":
        pid = PlotId(str(inp.get("plot_id", "")).strip())
        if str(pid) not in world.plots:
            return {"ok": False, "reason": "unknown plot"}
        return dict(claim_plot(world, party, pid))

    if name == "sim_survey_plot":
        pid = PlotId(str(inp.get("plot_id", "")).strip())
        if str(pid) not in world.plots:
            return {"ok": False, "reason": "unknown plot"}
        return dict(survey_plot(world, party, pid))

    if name == "sim_start_production":
        pid = PlotId(str(inp.get("plot_id", "")).strip())
        rid = str(inp.get("recipe_id", "")).strip()
        if str(pid) not in world.plots:
            return {"ok": False, "reason": "unknown plot"}
        if not rid:
            return {"ok": False, "reason": "missing recipe_id"}
        return dict(start_production_on_plot(world, party, pid, rid))

    if name == "sim_dispatch_shipment":
        mid = _material_id(inp.get("material"))
        if mid is None:
            return {"ok": False, "reason": "unknown material"}
        qty = _coerce_int(inp.get("qty"), 0)
        fp = PlotId(str(inp.get("from_plot_id", "")).strip())
        tp = PlotId(str(inp.get("to_plot_id", "")).strip())
        return dict(dispatch_shipment(world, party, mid, qty, fp, tp))

    return {"ok": False, "reason": f"unknown tool {name!r}"}


def plan_llm_party_once(world: World, party: PartyId) -> dict[str, Any]:
    """Run one Haiku planning session for ``party`` (must exist in ``world.llm_agents``)."""
    key = str(party)
    blob = world.llm_agents.get(key)
    if blob is None:
        return {"ok": False, "reason": "not an llm party"}

    cap = session_cap_micro_usd()
    if cap > 0 and world.llm_session_cost_micro_usd >= cap:
        log_event(
            world,
            "llm_cap",
            "Tier-3 session spend cap reached — skipping LLM calls until lower spend or higher cap.",
            party=key,
            spend_micro_usd=world.llm_session_cost_micro_usd,
            cap_micro_usd=cap,
        )
        return {"ok": False, "reason": "session_cap_reached"}

    system = str(blob.get("system_prompt", "You are a trading agent."))
    user = (
        "Current observation JSON:\n"
        + build_observation_json(world, party)
        + "\n\nMemory so far:\n"
        + str(blob.get("memory_summary", ""))[-3500:]
    )

    def on_tool(n: str, data: dict[str, Any]) -> dict[str, Any]:
        return execute_llm_tool(world, party, n, data)

    trace, summary, usage = run_haiku_tool_session(system=system, user_message=user, on_tool=on_tool)
    if trace == [{"event": "skipped", "reason": "no_anthropic_client"}]:
        return {"ok": False, "reason": "no_anthropic_client", "trace": trace}

    world.llm_session_input_tokens += int(usage.get("input_tokens", 0))
    world.llm_session_output_tokens += int(usage.get("output_tokens", 0))
    world.llm_session_cost_micro_usd += int(usage.get("cost_micro_usd", 0))

    lines = [f"tick {world.tick}:"]
    for row in trace:
        if row.get("event") == "tool":
            lines.append(f"  {row.get('name')} -> {row.get('result')}")
    if summary:
        lines.append(f"  note: {summary[:400]}")
    _append_memory(blob, "\n".join(lines))
    blob["last_plan_tick"] = world.tick
    log_event(
        world,
        "llm_plan",
        f"{party} LLM plan ({len(trace)} trace rows)",
        party=str(party),
        trace_rows=len(trace),
        usage=usage,
    )
    return {"ok": True, "party": key, "trace": trace, "summary": summary, "usage": usage}


def _append_memory(blob: dict[str, Any], line: str) -> None:
    prev = str(blob.get("memory_summary", ""))
    merged = (prev + "\n" + line).strip()
    blob["memory_summary"] = merged[-6000:]


def tick_tier3_llm_agents(world: World) -> list[dict[str, Any]]:
    """Run due Tier-3 planners (in world tick order, before ``world.tick`` increments)."""
    from realm.llm_haiku import make_client

    if make_client() is None:
        return []

    out: list[dict[str, Any]] = []
    cd = _cooldown_ticks()
    for key in sorted(world.llm_agents.keys()):
        party = PartyId(key)
        if party not in world.parties:
            continue
        blob = world.llm_agents[key]
        last = int(blob.get("last_plan_tick", -10**9))
        if world.tick - last < cd:
            continue
        out.append(plan_llm_party_once(world, party))
    return out

"""Anthropic Haiku client for Tier-3 agents (optional dependency).

Environment:
- ``ANTHROPIC_API_KEY`` — required for live calls.
- ``REALM_LLM_MODEL`` — defaults to ``claude-3-5-haiku-20241022``.
- ``REALM_LLM_MAX_TOKENS`` — completion budget (default ``1024``).
- ``REALM_LLM_SESSION_CAP_USD`` — max cumulative estimated spend per save/session (default ``2.0``).
- ``REALM_LLM_PRICE_INPUT_PER_MTOK_USD`` / ``REALM_LLM_PRICE_OUTPUT_PER_MTOK_USD`` — Haiku $/million tokens for cost estimates (defaults Haiku-tier placeholders).

If ``anthropic`` is not installed or the key is missing, ``make_client()`` returns ``None`` and
tick code skips LLM calls (CI / local dev without spend).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

ToolHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


def default_model() -> str:
    return os.environ.get("REALM_LLM_MODEL", "claude-3-5-haiku-20241022").strip()


def max_output_tokens() -> int:
    raw = os.environ.get("REALM_LLM_MAX_TOKENS", "1024").strip()
    try:
        n = int(raw)
    except ValueError:
        return 1024
    return max(256, min(n, 4096))


def session_cap_micro_usd() -> int:
    """Hard cap on cumulative session spend (micro-dollars: 1 == $1e-6)."""
    raw = os.environ.get("REALM_LLM_SESSION_CAP_USD", "2.0").strip()
    try:
        cap_usd = float(raw)
    except ValueError:
        cap_usd = 2.0
    cap_usd = max(0.0, min(cap_usd, 500.0))
    return int(cap_usd * 1_000_000)


def estimate_cost_micro_usd(*, input_tokens: int, output_tokens: int) -> int:
    """Rough USD cost from token counts using configurable $/million rates."""
    try:
        pin = float(os.environ.get("REALM_LLM_PRICE_INPUT_PER_MTOK_USD", "1.0"))
        pout = float(os.environ.get("REALM_LLM_PRICE_OUTPUT_PER_MTOK_USD", "5.0"))
    except ValueError:
        pin, pout = 1.0, 5.0
    usd = (max(0, input_tokens) / 1_000_000.0) * pin + (max(0, output_tokens) / 1_000_000.0) * pout
    return int(usd * 1_000_000)


def make_client() -> Any:
    if os.environ.get("REALM_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def _tool_defs() -> list[dict[str, Any]]:
    """Anthropic Messages ``tools`` schema."""
    mat = {
        "type": "string",
        "description": "Material id, e.g. timber, grain, clay, coal, iron_ore",
    }
    plot = {"type": "string", "description": "Plot id like p-0-0"}
    return [
        {
            "name": "sim_message_player",
            "description": (
                "Send a short in-character line to the human player (appears in their feed). "
                "Use sparingly; trading actions still require other tools."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Plain text to the player (max ~420 chars enforced server-side).",
                    },
                },
                "required": ["message"],
            },
        },
        {
            "name": "sim_place_buy_order",
            "description": "Rest a limit buy; escrows cash up to qty × max price.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "material": mat,
                    "qty": {"type": "integer", "minimum": 1},
                    "max_price_per_unit_cents": {"type": "integer", "minimum": 1},
                },
                "required": ["material", "qty", "max_price_per_unit_cents"],
            },
        },
        {
            "name": "sim_place_sell_order",
            "description": "List inventory for sale at a limit price.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "material": mat,
                    "qty": {"type": "integer", "minimum": 1},
                    "price_per_unit_cents": {"type": "integer", "minimum": 1},
                },
                "required": ["material", "qty", "price_per_unit_cents"],
            },
        },
        {
            "name": "sim_market_buy",
            "description": "Aggressive market buy at best asks until max_qty or cash runs out.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "material": mat,
                    "max_qty": {"type": "integer", "minimum": 1},
                },
                "required": ["material", "max_qty"],
            },
        },
        {
            "name": "sim_claim_plot",
            "description": "Claim an unowned plot adjacent to your strategy (must be unowned).",
            "input_schema": {
                "type": "object",
                "properties": {"plot_id": plot},
                "required": ["plot_id"],
            },
        },
        {
            "name": "sim_survey_plot",
            "description": "Pay to survey subsurface on a plot you own.",
            "input_schema": {
                "type": "object",
                "properties": {"plot_id": plot},
                "required": ["plot_id"],
            },
        },
        {
            "name": "sim_start_production",
            "description": "Start a recipe run on an owned plot (requires building + inputs).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "plot_id": plot,
                    "recipe_id": {"type": "string"},
                },
                "required": ["plot_id", "recipe_id"],
            },
        },
        {
            "name": "sim_dispatch_shipment",
            "description": "Ship inventory between two plots you own.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "material": mat,
                    "qty": {"type": "integer", "minimum": 1},
                    "from_plot_id": plot,
                    "to_plot_id": plot,
                },
                "required": ["material", "qty", "from_plot_id", "to_plot_id"],
            },
        },
        {
            "name": "sim_noop",
            "description": "Take no market action this planning window.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


def run_haiku_tool_session(
    *,
    system: str,
    user_message: str,
    on_tool: ToolHandler,
    max_rounds: int = 6,
) -> tuple[list[dict[str, Any]], str | None, dict[str, int]]:
    """
    Run a Haiku tool loop. Returns ``(trace, assistant_summary_text, usage_aggregate)``.
    ``usage_aggregate`` has ``input_tokens``, ``output_tokens``, ``cost_micro_usd``.
    """
    empty_usage = {"input_tokens": 0, "output_tokens": 0, "cost_micro_usd": 0}
    client = make_client()
    if client is None:
        return ([{"event": "skipped", "reason": "no_anthropic_client"}], None, empty_usage.copy())

    tools = _tool_defs()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    trace: list[dict[str, Any]] = []
    summary_text: str | None = None
    total_in = 0
    total_out = 0

    for round_i in range(max_rounds):
        resp = client.messages.create(
            model=default_model(),
            max_tokens=max_output_tokens(),
            system=system,
            tools=tools,
            messages=messages,
        )
        use = getattr(resp, "usage", None)
        if use is not None:
            total_in += int(getattr(use, "input_tokens", 0) or 0)
            total_out += int(getattr(use, "output_tokens", 0) or 0)
        trace.append(
            {
                "event": "assistant",
                "round": round_i,
                "stop_reason": getattr(resp, "stop_reason", None),
            }
        )

        tool_results: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif btype == "tool_use":
                uid = str(getattr(block, "id", "") or "")
                name = str(getattr(block, "name", "") or "")
                raw_in = getattr(block, "input", {}) or {}
                if not isinstance(raw_in, dict):
                    raw_in = {}
                out = on_tool(name, raw_in)
                trace.append({"event": "tool", "name": name, "input": raw_in, "result": out})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": uid,
                        "content": json.dumps(out),
                    }
                )

        if tool_results:
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        summary_text = "\n".join(p for p in text_parts if p).strip() or None
        break

    cost_micro = estimate_cost_micro_usd(input_tokens=total_in, output_tokens=total_out)
    usage_out = {"input_tokens": total_in, "output_tokens": total_out, "cost_micro_usd": cost_micro}
    return (trace, summary_text, usage_out)

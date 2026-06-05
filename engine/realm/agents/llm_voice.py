"""Settler voice lines for major life events (Haiku, optional Anthropic client).

Non-blocking: requests are queued and completed futures are applied on
``tick_settler_voice``. Rate-limited to three voice calls per game-day.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Literal

from realm.agents.llm_haiku import estimate_cost_micro_usd, make_client
from realm.core.ids import PartyId
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.world import World

SettlerVoiceEvent = Literal[
    "company_formed",
    "bankruptcy",
    "first_foundry",
    "acquisition_complete",
    "market_corner",
    "patent_granted",
]

_VOICE_MODEL_DEFAULT = "claude-haiku-4-5"
_VOICE_MAX_TOKENS = 60
_VOICE_TEMPERATURE = 0.9
_VOICE_TTL_TICKS = TICKS_PER_GAME_DAY // 24  # one in-game hour
_MAX_VOICE_CALLS_PER_GAME_DAY = 3
_SUFFIX = " Respond with ONLY the one sentence. No quotes, no attribution, no explanation."

_EVENT_TEMPLATES: dict[SettlerVoiceEvent, str] = {
    "company_formed": (
        "You are {party_display_name}, a settler entrepreneur who just formed a company "
        "with {partner_display_name}. In one sentence, what do you tell your new partner on day one?"
    ),
    "bankruptcy": (
        "You are {party_display_name}, a settler who just went bankrupt after {days_active} days. "
        "In one sentence, what's your final reflection as you leave the frontier?"
    ),
    "first_foundry": (
        "You are {party_display_name}, a settler who just built their first foundry. "
        "One sentence about what this means to you."
    ),
    "acquisition_complete": (
        "You are {party_display_name}, a settler who just acquired {target_display_name}'s operations. "
        "One sentence — what do you say publicly?"
    ),
    "market_corner": (
        "You are {party_display_name}, who just cornered the {material} market. One boastful sentence."
    ),
    "patent_granted": (
        "You are {party_display_name}, who just received a patent on {node_id}. "
        "One sentence about your discovery."
    ),
}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="realm_settler_llm")


def settler_voice_model() -> str:
    return (
        os.environ.get("REALM_SETTLER_VOICE_MODEL", "").strip()
        or os.environ.get("REALM_LLM_MODEL", "").strip()
        or _VOICE_MODEL_DEFAULT
    )


def _voice_state(world: World) -> dict[str, Any]:
    raw = world.scenario_state.setdefault("settler_voice", {})
    if not isinstance(raw, dict):
        world.scenario_state["settler_voice"] = {}
        raw = world.scenario_state["settler_voice"]
    return raw


def _display_name(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def _game_day(world: World) -> int:
    return int(world.tick) // TICKS_PER_GAME_DAY


def _cache_key(party: PartyId, event_type: SettlerVoiceEvent) -> str:
    return f"{party}|{event_type}"


def _cache_get(world: World, party: PartyId, event_type: SettlerVoiceEvent) -> str | None:
    st = _voice_state(world)
    cache = st.get("cache")
    if not isinstance(cache, dict):
        return None
    row = cache.get(_cache_key(party, event_type))
    if not isinstance(row, dict):
        return None
    expires = int(row.get("expires_tick", 0))
    if int(world.tick) > expires:
        return None
    text = str(row.get("text", "")).strip()
    return text or None


def _cache_put(
    world: World,
    party: PartyId,
    event_type: SettlerVoiceEvent,
    text: str,
) -> None:
    st = _voice_state(world)
    cache = st.setdefault("cache", {})
    if not isinstance(cache, dict):
        st["cache"] = {}
        cache = st["cache"]
    cache[_cache_key(party, event_type)] = {
        "text": text,
        "expires_tick": int(world.tick) + _VOICE_TTL_TICKS,
        "event_type": event_type,
    }


def _voice_calls_today(world: World) -> int:
    st = _voice_state(world)
    usage = st.get("daily_usage")
    if not isinstance(usage, dict):
        return 0
    day = _game_day(world)
    if int(usage.get("game_day", -1)) != day:
        return 0
    return int(usage.get("calls", 0))


def _record_voice_call(world: World) -> None:
    st = _voice_state(world)
    usage = st.setdefault("daily_usage", {"game_day": _game_day(world), "calls": 0})
    if not isinstance(usage, dict):
        usage = {"game_day": _game_day(world), "calls": 0}
        st["daily_usage"] = usage
    day = _game_day(world)
    if int(usage.get("game_day", -1)) != day:
        usage["game_day"] = day
        usage["calls"] = 0
    usage["calls"] = int(usage.get("calls", 0)) + 1


def _can_schedule_voice(world: World) -> bool:
    if make_client() is None:
        return False
    return _voice_calls_today(world) < _MAX_VOICE_CALLS_PER_GAME_DAY


def _build_prompt(event_type: SettlerVoiceEvent, event_data: dict[str, Any]) -> str:
    template = _EVENT_TEMPLATES[event_type]
    return template.format_map(event_data) + _SUFFIX


def _sanitize_one_sentence(raw: str) -> str:
    text = raw.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1].strip()
    first = re.split(r"[.!?]\s+", text, maxsplit=1)[0].strip()
    if first:
        text = first
    if len(text) > 280:
        text = text[:277].rstrip() + "..."
    return text


def _haiku_one_liner(prompt: str) -> tuple[str | None, dict[str, int]]:
    empty = {"input_tokens": 0, "output_tokens": 0, "cost_micro_usd": 0}
    client = make_client()
    if client is None:
        return None, empty
    try:
        resp = client.messages.create(
            model=settler_voice_model(),
            max_tokens=_VOICE_MAX_TOKENS,
            temperature=_VOICE_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return None, empty
    parts: list[str] = []
    total_in = 0
    total_out = 0
    use = getattr(resp, "usage", None)
    if use is not None:
        total_in = int(getattr(use, "input_tokens", 0) or 0)
        total_out = int(getattr(use, "output_tokens", 0) or 0)
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    text = _sanitize_one_sentence("\n".join(parts))
    usage = {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_micro_usd": estimate_cost_micro_usd(input_tokens=total_in, output_tokens=total_out),
    }
    return (text or None), usage


def record_settler_join_tick(world: World, party: PartyId) -> None:
    """Call when a settler enters the economy (for bankruptcy ``days_active``)."""
    if not str(party).startswith("settler_"):
        return
    st = _voice_state(world)
    joins = st.setdefault("join_tick", {})
    if not isinstance(joins, dict):
        st["join_tick"] = {}
        joins = st["join_tick"]
    joins.setdefault(str(party), int(world.tick))


def settler_days_active(world: World, party: PartyId) -> int:
    st = _voice_state(world)
    joins = st.get("join_tick")
    if isinstance(joins, dict):
        joined = joins.get(str(party))
        if joined is not None:
            return max(1, (int(world.tick) - int(joined)) // TICKS_PER_GAME_DAY)
    return max(1, int(world.tick) // TICKS_PER_GAME_DAY)


def _append_settler_voice(world: World, party: PartyId, text: str) -> None:
    display = _display_name(world, party)
    world.npc_messages_to_player.append(
        {
            "tick": world.tick,
            "from_party": str(party),
            "display_name": display,
            "text": text,
            "source": "settler_voice",
        }
    )
    if len(world.npc_messages_to_player) > 96:
        world.npc_messages_to_player = world.npc_messages_to_player[-96:]
    log_event(
        world,
        "npc_message",
        f"{display}: {text}",
        from_party=str(party),
        party=str(party),
        source="settler_voice",
    )


def _pending_queue(world: World) -> list[dict[str, Any]]:
    st = _voice_state(world)
    raw = st.setdefault("pending", [])
    if not isinstance(raw, list):
        st["pending"] = []
        raw = st["pending"]
    return raw


def generate_settler_voice(
    world: World,
    party: PartyId,
    event_type: SettlerVoiceEvent,
    event_data: dict[str, Any],
) -> None:
    """Queue a one-line voice for ``party``; never blocks the tick loop."""
    if world.scenario_id != "genesis":
        return
    if not str(party).startswith("settler_"):
        return
    if party not in world.parties:
        return

    cached = _cache_get(world, party, event_type)
    if cached:
        _append_settler_voice(world, party, cached)
        return

    st = _voice_state(world)
    inflight = st.setdefault("inflight", {})
    if not isinstance(inflight, dict):
        st["inflight"] = {}
        inflight = st["inflight"]
    key = _cache_key(party, event_type)
    if key in inflight:
        return

    if not _can_schedule_voice(world):
        return

    payload = dict(event_data)
    payload.setdefault("party_display_name", _display_name(world, party))
    prompt = _build_prompt(event_type, payload)

    def _run() -> tuple[str | None, dict[str, int]]:
        return _haiku_one_liner(prompt)

    fut: Future[tuple[str | None, dict[str, int]]] = _executor.submit(_run)
    _record_voice_call(world)
    inflight[key] = {
        "future_id": id(fut),
        "party": str(party),
        "event_type": event_type,
        "queued_tick": int(world.tick),
        "_future": fut,
    }
    _pending_queue(world).append(
        {
            "party": str(party),
            "event_type": event_type,
            "cache_key": key,
            "queued_tick": int(world.tick),
        }
    )


def tick_settler_voice(world: World) -> None:
    """Apply completed voice futures; drop stale jobs after one game-day."""
    if world.scenario_id != "genesis":
        return
    st = _voice_state(world)
    inflight = st.get("inflight")
    if not inflight:
        return
    if not isinstance(inflight, dict):
        return

    cutoff = int(world.tick) - TICKS_PER_GAME_DAY
    done_keys: list[str] = []
    for key, row in list(inflight.items()):
        if not isinstance(row, dict):
            done_keys.append(key)
            continue
        fut = row.get("_future")
        if not isinstance(fut, Future):
            done_keys.append(key)
            continue
        queued = int(row.get("queued_tick", 0))
        if queued < cutoff and not fut.done():
            fut.cancel()
            done_keys.append(key)
            continue
        if not fut.done():
            continue
        try:
            text, usage = fut.result(timeout=0)
        except Exception:
            done_keys.append(key)
            continue
        party = PartyId(str(row.get("party", "")))
        event_type = row.get("event_type")
        if text and party in world.parties and isinstance(event_type, str):
            _cache_put(world, party, event_type, text)  # type: ignore[arg-type]
            _append_settler_voice(world, party, text)
        micro = int(usage.get("cost_micro_usd", 0))
        st["session_cost_micro_usd"] = int(st.get("session_cost_micro_usd", 0)) + micro
        done_keys.append(key)

    for key in done_keys:
        inflight.pop(key, None)

    pending = _pending_queue(world)
    st["pending"] = [r for r in pending if isinstance(r, dict) and r.get("cache_key") in inflight]


def maybe_first_foundry_voice(world: World, party: PartyId) -> None:
    """Fire once per settler when a foundry build succeeds."""
    if not str(party).startswith("settler_"):
        return
    st = _voice_state(world)
    done = st.setdefault("first_foundry_done", set())
    if isinstance(done, list):
        done = set(str(x) for x in done)
        st["first_foundry_done"] = done
    if not isinstance(done, set):
        done = set()
        st["first_foundry_done"] = done
    ps = str(party)
    if ps in done:
        return
    has = any(
        b.get("party") == ps and b.get("building_id") == "foundry" for b in world.plot_buildings
    )
    if not has:
        return
    done.add(ps)
    generate_settler_voice(
        world,
        party,
        "first_foundry",
        {"party_display_name": _display_name(world, party)},
    )

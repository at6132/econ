"""Utility operator identity and monthly power statements."""

from __future__ import annotations

from typing import Any

from realm.core.ids import PartyId
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.world import World

UTILITY_PARTY_ID: PartyId = PartyId("frontier_grid_co")
UTILITY_DISPLAY_NAME: str = "Frontier Grid & Power Co."

_BILLING_PERIOD_TICKS: int = 30 * TICKS_PER_GAME_DAY


def seed_utility_operator(world: World) -> None:
    world.parties.add(UTILITY_PARTY_ID)
    world.party_display_names[str(UTILITY_PARTY_ID)] = UTILITY_DISPLAY_NAME
    util = world.scenario_state.setdefault("utility_operator", {})
    util["party"] = str(UTILITY_PARTY_ID)
    util["display_name"] = UTILITY_DISPLAY_NAME


def accrue_monthly_usage(
    world: World, party: PartyId, *, wh: int, cents: int
) -> None:
    if wh <= 0 and cents <= 0:
        return
    bucket: dict[str, Any] = world.scenario_state.setdefault("power_month_usage", {})
    row = bucket.setdefault(
        str(party),
        {"wh": 0, "cents": 0, "period_start_tick": int(world.tick)},
    )
    row["wh"] = int(row.get("wh", 0)) + int(wh)
    row["cents"] = int(row.get("cents", 0)) + int(cents)


def tick_monthly_utility_bills(world: World) -> None:
    """Emit a statement every 30 game-days for parties with recorded usage."""
    if int(world.tick) <= 0 or int(world.tick) % _BILLING_PERIOD_TICKS != 0:
        return
    bucket: dict[str, Any] = dict(world.scenario_state.get("power_month_usage") or {})
    if not bucket:
        return
    history: list[dict[str, Any]] = list(
        world.scenario_state.get("power_bill_history") or []
    )
    for party_s, row in list(bucket.items()):
        wh = int(row.get("wh", 0))
        cents = int(row.get("cents", 0))
        if wh <= 0 and cents <= 0:
            bucket.pop(party_s, None)
            continue
        kwh = wh / 1000.0
        bill_id = f"bill-{world.tick}-{party_s}"
        entry = {
            "bill_id": bill_id,
            "party": party_s,
            "utility": str(UTILITY_PARTY_ID),
            "utility_name": UTILITY_DISPLAY_NAME,
            "period_ticks": _BILLING_PERIOD_TICKS,
            "tick": int(world.tick),
            "energy_wh": wh,
            "energy_kwh": round(kwh, 2),
            "total_cents": cents,
        }
        history.append(entry)
        if len(history) > 24:
            history = history[-24:]
        log_event(
            world,
            "power_bill",
            (
                f"{UTILITY_DISPLAY_NAME}: monthly statement for {party_s} — "
                f"{kwh:.1f} kWh, ${cents / 100:.2f} (paid from grid settlements this period)"
            ),
            party=party_s,
            utility=str(UTILITY_PARTY_ID),
            energy_wh=wh,
            total_cents=cents,
            bill_id=bill_id,
        )
        if party_s == "player":
            world.scenario_state.setdefault("player_messages", [])
            msgs = world.scenario_state["player_messages"]
            if isinstance(msgs, list):
                msgs.append(
                    {
                        "tick": int(world.tick),
                        "kind": "power_bill",
                        "text": (
                            f"{UTILITY_DISPLAY_NAME} — {kwh:.1f} kWh this month, "
                            f"${cents / 100:.2f} charged to your account."
                        ),
                        "bill_id": bill_id,
                    }
                )
                if len(msgs) > 40:
                    del msgs[:-40]
        bucket.pop(party_s, None)
    world.scenario_state["power_month_usage"] = bucket
    world.scenario_state["power_bill_history"] = history


def power_bills_for_party(world: World, party: PartyId) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in world.scenario_state.get("power_bill_history") or []:
        if isinstance(row, dict) and str(row.get("party", "")) == str(party):
            out.append(dict(row))
    return out

"""Player-configurable price alerts (Sprint 4 — Phase D.1).

Alerts are passive: when a watched best-ask crosses the configured threshold,
the engine appends one ``price_alert``-kind row to ``world.world_feed_log``.
There is no modal, no interrupt, and no prescriptive language — the player
either notices in the feed or doesn't.

State lives in ``world.scenario_state["player_price_alerts"]`` as a list of
dicts so it persists through snapshots.
"""

from __future__ import annotations

from typing import Any

from realm.events.event_log import log_event
from realm.markets import best_resting_ask_cents
from realm.core.ids import MaterialId
from realm.world import World


__all__ = [
    "add_price_alert",
    "remove_price_alert",
    "tick_price_alerts",
]


def _alerts(world: World) -> list[dict]:
    raw = world.scenario_state.setdefault("player_price_alerts", [])
    if not isinstance(raw, list):
        world.scenario_state["player_price_alerts"] = []
        raw = world.scenario_state["player_price_alerts"]
    return raw


def _seq(world: World) -> int:
    raw = world.scenario_state.setdefault("next_price_alert_seq", 0)
    if not isinstance(raw, int):
        raw = 0
    raw += 1
    world.scenario_state["next_price_alert_seq"] = raw
    return raw


def add_price_alert(
    world: World, material: str, condition: str, threshold_cents: int
) -> dict[str, Any]:
    if condition not in ("below", "above"):
        return {"ok": False, "reason": "condition must be 'below' or 'above'"}
    if threshold_cents <= 0:
        return {"ok": False, "reason": "threshold_cents must be positive"}
    alert_id = f"pa-{_seq(world)}"
    alert = {
        "alert_id": alert_id,
        "material": str(material),
        "condition": condition,
        "threshold_cents": int(threshold_cents),
        "triggered_at_tick": None,
        "active": True,
        "created_at_tick": int(world.tick),
        "last_known_cents": None,
    }
    _alerts(world).append(alert)
    log_event(
        world,
        "price_alert_added",
        f"Player added price alert for {material} {condition} {threshold_cents}¢ ({alert_id})",
        alert_id=alert_id,
        material=str(material),
        condition=condition,
        threshold_cents=int(threshold_cents),
    )
    return {"ok": True, "alert_id": alert_id, "alert": dict(alert)}


def remove_price_alert(world: World, alert_id: str) -> dict[str, Any]:
    alerts = _alerts(world)
    for i, a in enumerate(alerts):
        if str(a.get("alert_id", "")) == str(alert_id):
            alerts.pop(i)
            log_event(
                world,
                "price_alert_removed",
                f"Player removed price alert {alert_id}",
                alert_id=str(alert_id),
            )
            return {"ok": True, "alert_id": str(alert_id)}
    return {"ok": False, "reason": "unknown alert"}


def _condition_met(condition: str, threshold: int, price: int) -> bool:
    if condition == "below":
        return price < threshold
    return price > threshold


def tick_price_alerts(world: World) -> None:
    """Fire any alerts whose condition is currently met (idempotent per crossing).

    An alert that fires won't refire until the price has *recovered* (crossed
    back to the non-firing side of the threshold). The ``triggered_at_tick``
    field records the most recent firing — non-None means we're sitting on the
    triggered side.
    """
    alerts = _alerts(world)
    if not alerts:
        return
    for alert in alerts:
        if not bool(alert.get("active", True)):
            continue
        material = str(alert.get("material", ""))
        if not material:
            continue
        threshold = int(alert.get("threshold_cents", 0))
        condition = str(alert.get("condition", ""))
        price = best_resting_ask_cents(world, MaterialId(material))
        if price is None:
            continue
        alert["last_known_cents"] = int(price)
        currently_met = _condition_met(condition, threshold, int(price))
        already_triggered = alert.get("triggered_at_tick") is not None
        if currently_met and not already_triggered:
            alert["triggered_at_tick"] = int(world.tick)
            direction = "dropped below" if condition == "below" else "rose above"
            log_event(
                world,
                "world_feed",
                f"ALERT: {material} {direction} {threshold}¢ — currently {price}¢.",
                feed_source="price_alert",
                kind_tag="price_alert",
                material=material,
                threshold_cents=threshold,
                price_cents=int(price),
                alert_id=str(alert.get("alert_id", "")),
            )
        elif not currently_met and already_triggered:
            alert["triggered_at_tick"] = None

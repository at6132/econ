"""Plot buildings — Phase 1: pay cash, record on plot; storage + recipe labor modifiers where implemented."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId, PlotId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World

# Small costs so early game stays liquid (Phase 1 ugly-but-functional).
BUILDINGS: dict[str, dict[str, int | str]] = {
    "field_stockade": {
        "label": "Field stockade (+5k storage units)",
        "cost_cents": 25_000,
    },
    "tool_cache": {
        "label": "Tool cache (−10% recipe labor cash on this plot)",
        "cost_cents": 50_000,
    },
    "watch_hut": {
        "label": "Watch hut (−3% recipe labor cash on this plot)",
        "cost_cents": 15_000,
    },
}


def building_catalog_public() -> list[dict]:
    return [
        {"id": bid, "label": str(spec["label"]), "cost_cents": int(spec["cost_cents"])}
        for bid, spec in sorted(BUILDINGS.items(), key=lambda x: x[0])
    ]


def build_on_plot(world: World, party: PartyId, plot_id: PlotId, building_id: str) -> dict:
    """Spend cash; attach a building record to an owned plot (no recipe unlock yet)."""
    spec = BUILDINGS.get(building_id)
    if spec is None:
        return {"ok": False, "reason": "unknown building"}
    cost = int(spec["cost_cents"])
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < cost:
        return {"ok": False, "reason": "insufficient cash"}
    pay = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=cost,
    )
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}
    label = str(spec["label"])
    world.plot_buildings.append(
        {
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": building_id,
            "label": label,
            "cost_cents": cost,
        }
    )
    log_event(
        world,
        "build",
        f"{party} built {label} on {plot_id} for ${cost / 100:.2f}",
        party=str(party),
        plot_id=str(plot_id),
        building_id=building_id,
        cost_cents=cost,
    )
    return {"ok": True, "building_id": building_id}

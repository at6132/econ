"""Law 5 — building decay and maintenance."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.production.buildings import build_on_plot
from realm.production.decay import (
    BUILDING_CONDITION_FULL_BPS,
    MAINTENANCE_COST_DIVISOR,
    maintain_building,
    tick_building_decay,
)
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.world.tick import advance_tick
from realm.world import bootstrap_frontier

from plot_helpers import claimable_land_plot_id, first_land_plot_id


def test_tick_building_decay_reduces_condition() -> None:
    w = bootstrap_frontier(seed=3, grid_width=2, grid_height=2)
    w.plot_buildings.append(
        {
            "instance_id": "btest01",
            "condition_bps": BUILDING_CONDITION_FULL_BPS,
            "plot_id": "p-0-0",
            "party": "player",
            "building_id": "watch_hut",
            "label": "Watch",
            "cost_cents": 15_000,
        }
    )
    tick_building_decay(w)
    assert w.plot_buildings[-1]["condition_bps"] < BUILDING_CONDITION_FULL_BPS


def test_maintenance_fee_is_max_of_floor_and_build_cost_fraction() -> None:
    w = bootstrap_frontier(seed=41, grid_width=3, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    assert build_on_plot(w, PartyId("player"), pid, "watch_hut")["ok"] is True
    row = next(b for b in w.plot_buildings if b.get("building_id") == "watch_hut")
    row.pop("completes_at_tick", None)
    base = int(row["cost_cents"])
    expected = max(1_000, base // MAINTENANCE_COST_DIVISOR)
    row["condition_bps"] = 1_000
    r = maintain_building(w, PartyId("player"), str(row["instance_id"]))
    assert r["ok"] is True
    assert r["fee_cents"] == expected


def test_maintain_building_restores_condition_and_conserves_ledger_total() -> None:
    w = bootstrap_frontier(seed=4, grid_width=3, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    assert build_on_plot(w, PartyId("player"), pid, "watch_hut")["ok"] is True
    row = next(b for b in w.plot_buildings if b.get("building_id") == "watch_hut")
    row.pop("completes_at_tick", None)
    iid = str(row["instance_id"])
    row["condition_bps"] = 1_000
    total = w.ledger.total_cents()
    cash_before = w.ledger.balance(party_cash_account(PartyId("player")))
    r = maintain_building(w, PartyId("player"), iid)
    assert r["ok"] is True
    assert isinstance(r.get("fee_cents"), int)
    assert w.ledger.total_cents() == total
    assert w.ledger.balance(party_cash_account(PartyId("player"))) == cash_before - int(r["fee_cents"])
    assert row["condition_bps"] == BUILDING_CONDITION_FULL_BPS


def test_production_labor_bonus_requires_effective_building_condition() -> None:
    from realm.production import _labor_bps_for_plot

    w = bootstrap_frontier(seed=6, grid_width=2, grid_height=2)
    plot_id = PlotId("p-0-0")
    party = PartyId("player")
    w.plot_buildings.append(
        {
            "instance_id": "blow01",
            "condition_bps": 500,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": "tool_cache",
            "label": "Tools",
            "cost_cents": 25_000,
        }
    )
    assert _labor_bps_for_plot(w, party, plot_id) == 10_000
    w.plot_buildings[-1]["condition_bps"] = 10_000
    assert _labor_bps_for_plot(w, party, plot_id) < 10_000


def test_decay_runs_in_advance_tick() -> None:
    w = bootstrap_frontier(seed=7, grid_width=2, grid_height=2)
    w.plot_buildings.append(
        {
            "instance_id": "btick01",
            "condition_bps": BUILDING_CONDITION_FULL_BPS,
            "plot_id": "p-0-0",
            "party": "player",
            "building_id": "field_stockade",
            "label": "Stockade",
            "cost_cents": 30_000,
        }
    )
    before = w.plot_buildings[-1]["condition_bps"]
    advance_tick(w)
    assert w.plot_buildings[-1]["condition_bps"] < before

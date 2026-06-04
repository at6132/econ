"""Company registry — equity pools with ledger-backed cash accounts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from realm.core.ids import AccountId, PartyId
from realm.world import World


@dataclass(slots=True)
class Company:
    company_id: str
    name: str
    founded_tick: int
    founding_party: str
    share_registry: dict[str, int]
    total_shares: int
    managed_plots: list[str]
    cash_account: str
    hq_plot_id: str | None
    era_unlocked: str


def company_cash_account(company_id: str) -> AccountId:
    return AccountId(f"cash:{company_id}")


def _companies_raw(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("companies", {})
    if not isinstance(raw, dict):
        world.scenario_state["companies"] = {}
        raw = world.scenario_state["companies"]
    return raw


def company_to_dict(c: Company) -> dict[str, Any]:
    return {
        "company_id": c.company_id,
        "name": c.name,
        "founded_tick": int(c.founded_tick),
        "founding_party": c.founding_party,
        "share_registry": dict(c.share_registry),
        "total_shares": int(c.total_shares),
        "managed_plots": list(c.managed_plots),
        "cash_account": c.cash_account,
        "hq_plot_id": c.hq_plot_id,
        "era_unlocked": c.era_unlocked,
    }


def company_from_dict(d: dict[str, Any]) -> Company:
    return Company(
        company_id=str(d["company_id"]),
        name=str(d["name"]),
        founded_tick=int(d["founded_tick"]),
        founding_party=str(d["founding_party"]),
        share_registry={str(k): int(v) for k, v in dict(d.get("share_registry") or {}).items()},
        total_shares=int(d.get("total_shares", 0)),
        managed_plots=[str(p) for p in list(d.get("managed_plots") or [])],
        cash_account=str(d["cash_account"]),
        hq_plot_id=str(d["hq_plot_id"]) if d.get("hq_plot_id") else None,
        era_unlocked=str(d.get("era_unlocked", "industrial")),
    )


def get_companies(world: World) -> dict[str, Company]:
    out: dict[str, Company] = {}
    for cid, row in _companies_raw(world).items():
        if isinstance(row, dict):
            out[str(cid)] = company_from_dict(row)
    return out


def get_company(world: World, company_id: str) -> Company | None:
    row = _companies_raw(world).get(company_id)
    if not isinstance(row, dict):
        return None
    return company_from_dict(row)


def store_company(world: World, company: Company) -> None:
    _companies_raw(world)[company.company_id] = company_to_dict(company)


def company_for_party(world: World, party: PartyId) -> Company | None:
    key = str(party)
    for company in get_companies(world).values():
        if key in company.share_registry:
            return company
    return None


def next_company_id(world: World) -> str:
    st = world.scenario_state.setdefault("corporations", {})
    if not isinstance(st, dict):
        world.scenario_state["corporations"] = {}
        st = world.scenario_state["corporations"]
    seq = int(st.get("next_company_seq", 1))
    st["next_company_seq"] = seq + 1
    return f"co_{seq:04d}"


def party_plot_ids(world: World, party: PartyId) -> list[str]:
    return sorted(str(p.plot_id) for p in world.plots.values() if p.owner == party)


def current_era_for_party(world: World, party: PartyId) -> str:
    from realm.research.tech_tree import ERAS

    from realm.research.research_lab import _eras_unlocked_for_party  # inline: era lookup only

    unlocked = _eras_unlocked_for_party(world, party)
    order = list(ERAS.keys())
    best = "industrial"
    best_idx = -1
    for era_id in unlocked:
        if era_id in order and order.index(era_id) > best_idx:
            best_idx = order.index(era_id)
            best = era_id
    return best


def merge_company_eras(world: World, party_a: PartyId, party_b: PartyId) -> str:
    from realm.research.tech_tree import ERAS

    ea = current_era_for_party(world, party_a)
    eb = current_era_for_party(world, party_b)
    order = list(ERAS.keys())
    if order.index(ea) >= order.index(eb):
        return ea
    return eb

"""Player-authored recipes and materials (open-ended production extension)."""

from __future__ import annotations

from typing import Any

from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.materials import MATERIALS
from realm.production.recipes import RECIPES, Recipe
from realm.world import World, ensure_party_recipe_book

_CUSTOM_RECIPES_KEY = "custom_recipes"
_CUSTOM_MATERIALS_KEY = "custom_materials"
_REGISTER_MATERIAL_FEE_CENTS = 5_000
_REGISTER_RECIPE_FEE_CENTS = 10_000


def custom_recipes_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.get(_CUSTOM_RECIPES_KEY)
    if isinstance(raw, dict):
        return raw
    world.scenario_state[_CUSTOM_RECIPES_KEY] = {}
    return world.scenario_state[_CUSTOM_RECIPES_KEY]


def _custom_materials(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.get(_CUSTOM_MATERIALS_KEY)
    if isinstance(raw, dict):
        return raw
    world.scenario_state[_CUSTOM_MATERIALS_KEY] = {}
    return world.scenario_state[_CUSTOM_MATERIALS_KEY]


def material_exists(world: World, material_id: str) -> bool:
    mid = MaterialId(str(material_id))
    if mid in MATERIALS:
        return True
    return str(material_id) in _custom_materials(world)


def get_recipe(world: World, recipe_id: str) -> Recipe | None:
    if recipe_id in RECIPES:
        return RECIPES[recipe_id]
    row = custom_recipes_store(world).get(recipe_id)
    if not isinstance(row, dict):
        return None
    inputs = {
        MaterialId(str(k)): int(v)
        for k, v in (row.get("inputs") or {}).items()
    }
    outputs = {
        MaterialId(str(k)): int(v)
        for k, v in (row.get("outputs") or {}).items()
    }
    return Recipe(
        recipe_id=str(row.get("recipe_id", recipe_id)),
        display_name=str(row.get("display_name", recipe_id)),
        inputs=inputs,
        outputs=outputs,
        duration_ticks=int(row.get("duration_ticks", 60)),
        labor_cents=int(row.get("labor_cents", 0)),
        requires_building_id=str(row.get("requires_building_id", "")),
        requires_discovery=bool(row.get("requires_discovery", False)),
    )


def custom_recipes_for_party(world: World, party: PartyId) -> list[dict[str, Any]]:
    ps = str(party)
    out: list[dict[str, Any]] = []
    for rid, row in sorted(custom_recipes_store(world).items()):
        if not isinstance(row, dict):
            continue
        if str(row.get("creator_party", "")) != ps and not bool(row.get("is_public", False)):
            continue
        out.append({**row, "recipe_id": rid, "is_custom": True})
    return out


def custom_materials_public(world: World) -> list[dict[str, Any]]:
    return [
        {
            "material_id": mid,
            "display_name": str(row.get("display_name", mid)),
            "category": str(row.get("category", "processed")),
            "creator_party": str(row.get("creator_party", "")),
        }
        for mid, row in sorted(_custom_materials(world).items())
        if isinstance(row, dict)
    ]


def _next_custom_recipe_id(world: World) -> str:
    seq = int(world.scenario_state.get("next_custom_recipe_seq", 0)) + 1
    world.scenario_state["next_custom_recipe_seq"] = seq
    return f"custom_recipe_{seq}"


def _slug_material_id(raw: str) -> str:
    s = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw.strip().lower())
    s = s.strip("_")
    return s[:48] if s else "matter"


def register_custom_material(
    world: World,
    party: PartyId,
    display_name: str,
    category: str = "processed",
    material_id: str = "",
) -> dict[str, Any]:
    if not display_name or len(display_name) > 80:
        return {"ok": False, "reason": "display_name must be 1–80 characters"}
    cat = str(category).strip().lower() or "processed"
    if cat not in ("ore", "organic", "processed", "energy", "construction", "tool"):
        return {"ok": False, "reason": "invalid category"}
    mid = _slug_material_id(material_id or display_name)
    if mid in MATERIALS:
        return {"ok": False, "reason": "material id conflicts with catalog material"}
    mats = _custom_materials(world)
    if mid in mats:
        return {"ok": False, "reason": "material already registered"}
    fee = _REGISTER_MATERIAL_FEE_CENTS
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < fee:
        return {"ok": False, "reason": f"need ${fee / 100:.2f} to register material"}
    pay = world.ledger.transfer(debit=cash, credit=system_reserve_account(), amount_cents=fee)
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}
    mats[mid] = {
        "display_name": display_name,
        "category": cat,
        "creator_party": str(party),
    }
    return {"ok": True, "material_id": mid, "fee_cents": fee}


def create_custom_recipe(
    world: World,
    party: PartyId,
    display_name: str,
    inputs: dict[str, int],
    outputs: dict[str, int],
    duration_ticks: int,
    labor_cents: int,
    requires_building_id: str,
    *,
    is_public: bool = False,
) -> dict[str, Any]:
    if not display_name or len(display_name) > 80:
        return {"ok": False, "reason": "display_name must be 1–80 characters"}
    if duration_ticks < 1:
        return {"ok": False, "reason": "duration_ticks must be positive"}
    if not outputs:
        return {"ok": False, "reason": "recipe must have at least one output"}
    total_out = sum(int(v) for v in outputs.values())
    total_in = sum(int(v) for v in inputs.values())
    if total_out <= 0:
        return {"ok": False, "reason": "output qty must be positive"}
    for mid in list(inputs.keys()) + list(outputs.keys()):
        if not material_exists(world, str(mid)):
            return {
                "ok": False,
                "reason": f"unknown material '{mid}' — register it first or use catalog materials",
            }
    fee = _REGISTER_RECIPE_FEE_CENTS
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < fee:
        return {"ok": False, "reason": f"need ${fee / 100:.2f} to register recipe"}
    pay = world.ledger.transfer(debit=cash, credit=system_reserve_account(), amount_cents=fee)
    if isinstance(pay, MoneyErr):
        return {"ok": False, "reason": pay.reason}
    rid = _next_custom_recipe_id(world)
    row = {
        "recipe_id": rid,
        "display_name": display_name,
        "inputs": {str(k): int(v) for k, v in inputs.items()},
        "outputs": {str(k): int(v) for k, v in outputs.items()},
        "duration_ticks": int(duration_ticks),
        "labor_cents": int(labor_cents),
        "requires_building_id": str(requires_building_id),
        "requires_discovery": False,
        "creator_party": str(party),
        "is_public": bool(is_public),
    }
    custom_recipes_store(world)[rid] = row
    book = ensure_party_recipe_book(world, party)
    book.add(rid)
    return {"ok": True, "recipe_id": rid, "fee_cents": fee}

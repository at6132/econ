"""Plot schematic — linear recipe-chain validation (planning aid, Law 10).

Matches client logic in ``web/app/plotSchematic.ts``: simulate inventory after each step;
does not model labor, energy cost, or concurrent production runs.
"""

from __future__ import annotations

from realm.ids import PartyId
from realm.recipe_sites import recipe_allowed_on_terrain, terrain_allows_workshop
from realm.recipes import recipe_public_list
from realm.world import Plot, World


def validate_linear_recipe_chain(
    world: World, party: PartyId, chain_recipe_ids: list[str], *, plot: Plot
) -> dict:
    """Return ``{ok: true, final_inventory}`` or ``{ok: false, errors: [...]}``."""
    catalog_list = recipe_public_list()
    by_id = {r["id"]: r for r in catalog_list}

    bucket = world.inventory.stock.get(party, {})
    inv: dict[str, int] = {str(k): int(v) for k, v in bucket.items()}
    errors: list[str] = []

    if not terrain_allows_workshop(plot.terrain):
        errors.append(f"This plot ({plot.terrain.value}) cannot host workshop chains — pick dry land.")

    for i, rid in enumerate(chain_recipe_ids):
        if errors:
            break
        r = by_id.get(rid)
        if r is None:
            errors.append(f"Step {i + 1}: unknown recipe “{rid}”.")
            break
        if not recipe_allowed_on_terrain(plot.terrain, rid):
            display = str(r.get("display_name", rid))
            errors.append(
                f"Step {i + 1} — {display}: not available on this plot "
                f"(terrain {plot.terrain.value}).",
            )
            break
        display = str(r.get("display_name", rid))
        inputs: dict[str, int] = r.get("inputs") or {}
        for mat, need in inputs.items():
            have = inv.get(mat, 0)
            if have < need:
                errors.append(
                    f"Step {i + 1} — {display}: need {need}× {mat} ({have} available after previous steps).",
                )
        if errors:
            break

        for mat, need in inputs.items():
            nxt = inv.get(mat, 0) - need
            if nxt <= 0:
                inv.pop(mat, None)
            else:
                inv[mat] = nxt
        outputs: dict[str, int] = r.get("outputs") or {}
        for mat, add in outputs.items():
            inv[mat] = inv.get(mat, 0) + add

    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "final_inventory": inv}

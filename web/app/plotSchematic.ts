/**
 * Linear recipe-chain validation for the plot schematic (planning aid).
 * Simulates inventory after each step; does not model labor, time, or plot concurrency.
 */

export type SchematicRecipe = {
  id: string;
  display_name: string;
  inputs: Record<string, number>;
  outputs: Record<string, number>;
};

export function validateLinearRecipeChain(
  catalog: SchematicRecipe[],
  starterInv: Record<string, number>,
  chainIds: string[],
): { ok: true; finalInventory: Record<string, number> } | { ok: false; errors: string[] } {
  const byId = new Map(catalog.map((r) => [r.id, r]));
  const inv: Record<string, number> = { ...starterInv };
  const errors: string[] = [];

  for (let i = 0; i < chainIds.length; i++) {
    const rid = chainIds[i];
    const r = byId.get(rid);
    if (!r) {
      errors.push(`Step ${i + 1}: unknown recipe “${rid}”.`);
      break;
    }
    for (const [mat, need] of Object.entries(r.inputs)) {
      const have = inv[mat] ?? 0;
      if (have < need) {
        errors.push(
          `Step ${i + 1} — ${r.display_name}: need ${need}× ${mat} (${have} available after previous steps).`,
        );
      }
    }
    if (errors.length) break;

    for (const [mat, need] of Object.entries(r.inputs)) {
      const next = (inv[mat] ?? 0) - need;
      if (next <= 0) delete inv[mat];
      else inv[mat] = next;
    }
    for (const [mat, add] of Object.entries(r.outputs)) {
      inv[mat] = (inv[mat] ?? 0) + add;
    }
  }

  if (errors.length) return { ok: false, errors };
  return { ok: true, finalInventory: inv };
}

export function reorderChain<T>(items: T[], fromIndex: number, toIndex: number): T[] {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= items.length || toIndex >= items.length) {
    return items;
  }
  const next = [...items];
  const [row] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, row);
  return next;
}

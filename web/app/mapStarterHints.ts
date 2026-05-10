type PlotRef = { id: string; x: number; y: number; terrain: string; owner: string | null };

/** Unclaimed land types to avoid nudging brand-new players onto. */
const STARTER_AVOID_TERRAIN = new Set(["water_deep", "water_shallow"]);

function terrainRank(terrain: string): number {
  if (terrain === "plains") return 0;
  if (terrain === "forest") return 1;
  if (terrain === "swamp") return 4;
  if (terrain === "mountain") return 3;
  return 2;
}

/**
 * Pick a few unclaimed plots near the grid origin for a soft “first claim” pulse.
 * Purely client-side; matches Frontier bootstrap (player begins with no deeds).
 */
export function computeStarterHintPlotIds(plots: PlotRef[], maxHints: number): Set<string> {
  const candidates = plots.filter((p) => !p.owner && !STARTER_AVOID_TERRAIN.has(p.terrain));
  candidates.sort((a, b) => {
    const da = a.x + a.y;
    const db = b.x + b.y;
    if (da !== db) return da - db;
    const tr = terrainRank(a.terrain) - terrainRank(b.terrain);
    if (tr !== 0) return tr;
    return a.id.localeCompare(b.id);
  });
  return new Set(candidates.slice(0, maxHints).map((p) => p.id));
}

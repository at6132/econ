import type { MarketHistorySnap } from "./MarketHistoryChart";

/** Default commodities shown in the Bazaar even before the book has data. */
export const BAZAAR_DEFAULT_MATERIALS = ["grain", "timber", "coal", "clay", "electricity"] as const;

type WorldMarketSlice = {
  market_history?: MarketHistorySnap[];
  market_asks?: { material: string }[];
  market_bids?: { material: string }[];
};

export function collectBazaarSymbolIds(w: WorldMarketSlice | null | undefined): string[] {
  const set = new Set<string>([...BAZAAR_DEFAULT_MATERIALS]);
  for (const h of w?.market_history ?? []) {
    for (const k of Object.keys(h.best_asks_cents ?? {})) set.add(k);
    for (const k of Object.keys(h.best_bids_cents ?? {})) set.add(k);
  }
  for (const a of w?.market_asks ?? []) set.add(a.material);
  for (const b of w?.market_bids ?? []) set.add(b.material);
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

export function normalizeBazaarSymbolId(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "");
}

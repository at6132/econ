import type { MarketHistorySnap } from "./MarketHistoryChart";

/** Best-effort ¢/unit from the latest recorded book (mid if both bid and ask exist). */
export function bookMidpointCentsPerUnit(history: MarketHistorySnap[] | undefined, material: string): number | null {
  if (!history?.length) return null;
  const last = history[history.length - 1];
  const ask = last.best_asks_cents?.[material];
  const bid = last.best_bids_cents?.[material];
  if (ask != null && bid != null) return (ask + bid) / 2;
  if (ask != null) return ask;
  if (bid != null) return bid;
  return null;
}

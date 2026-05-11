/**
 * Human-facing labels and money/time formatting for Frontier UI.
 * Keep engine/API ids unchanged — translate only at display boundaries.
 */

/** Sync with `engine/realm/movement.py` */
export const SHIP_BASE_FEE_CENTS = 100;
export const SHIP_PER_TILE_CENTS = 50;
export const SHIP_TRANSIT_BUFFER_TICKS = 1;

const PARTY_DISPLAY: Record<string, string> = {
  player: "You",
  t1_consumer: "Townfolk",
  npc_grain_vendor: "Grain vendor",
  t1_timber_merchant: "Timber merchant",
  t1_lumber_buyer: "Lumber buyer",
  t1_coal_vendor: "Coal vendor",
  t1_clay_vendor: "Clay vendor",
  t1_electricity_buyer: "Power buyer",
};

export function displayParty(
  id: string | null | undefined,
  partyDisplayNames?: Readonly<Record<string, string>> | null,
): string {
  if (id == null || id === "") return "—";
  const custom = partyDisplayNames?.[id];
  if (custom) return custom;
  const mapped = PARTY_DISPLAY[id];
  if (mapped) return mapped;
  if (id.startsWith("t1_")) {
    return id
      .slice(3)
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(" ");
  }
  if (id.startsWith("npc_")) {
    return id
      .slice(4)
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(" ");
  }
  return id
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function displayMaterial(id: string): string {
  return id
    .split("_")
    .map((w) => (w.length ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(" ");
}

export function formatUsdFromCents(cents: number | null | undefined): string {
  if (cents == null || !Number.isFinite(cents)) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}

export function formatUsdPerUnitFromCentsPerUnit(centsPerUnit: number | null | undefined): string {
  return formatUsdFromCents(centsPerUnit ?? null);
}

export function parseDollarsToCents(s: string): number | null {
  const t = s.trim();
  if (t === "") return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

export function formatQtyTimesMaterial(qty: number, materialId: string): string {
  return `${qty}× ${displayMaterial(materialId)}`;
}

export function parsePlotCoords(plotId: string): { x: number; y: number } | null {
  const m = /^p-(\d+)-(\d+)$/.exec(plotId);
  if (!m) return null;
  return { x: Number(m[1]), y: Number(m[2]) };
}

export function manhattanPlotIds(a: string, b: string): number | null {
  const pa = parsePlotCoords(a);
  const pb = parsePlotCoords(b);
  if (!pa || !pb) return null;
  return Math.abs(pa.x - pb.x) + Math.abs(pa.y - pb.y);
}

export function previewShipFeeCents(fromPlotId: string, toPlotId: string): number | null {
  const d = manhattanPlotIds(fromPlotId, toPlotId);
  if (d == null || d === 0) return null;
  return SHIP_BASE_FEE_CENTS + d * SHIP_PER_TILE_CENTS;
}

export function previewShipArriveTick(currentTick: number, fromPlotId: string, toPlotId: string): number | null {
  const d = manhattanPlotIds(fromPlotId, toPlotId);
  if (d == null || d === 0) return null;
  return currentTick + d * SHIP_TRANSIT_BUFFER_TICKS + SHIP_TRANSIT_BUFFER_TICKS;
}

export function formatApproxDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "~0s";
  const s = Math.max(1, Math.round(ms / 1000));
  if (s < 90) return `~${s}s`;
  const m = Math.round(s / 60);
  return `~${m}m`;
}

/** Relative ticks from now with rough wall-clock hint (solo client timer). */
export function formatRelativeTicksFromNow(
  relTicks: number,
  msPerSimTick: number,
): string {
  if (relTicks <= 0) return "now";
  return `~${relTicks} tick${relTicks === 1 ? "" : "s"} (${formatApproxDurationMs(relTicks * msPerSimTick)})`;
}

/** Absolute deadline tick + delta from current world tick. */
export function formatDeliverBy(
  worldTick: number,
  deliverByTick: number | null | undefined,
  msPerSimTick: number,
): string {
  if (deliverByTick == null || !Number.isFinite(deliverByTick)) return "—";
  const rel = deliverByTick - worldTick;
  if (rel <= 0) return `tick ${deliverByTick} (past due)`;
  return `tick ${deliverByTick} · ${formatRelativeTicksFromNow(rel, msPerSimTick)} from now`;
}

/** Best-effort prettify of engine event_log lines (party + material tokens). */
export function prettifyChronicleMessage(
  raw: string,
  partyDisplayNames?: Readonly<Record<string, string>> | null,
): string {
  let s = raw;
  const lead = /^([a-z0-9_]+)(?=\s*:)/;
  const lm = lead.exec(s);
  if (lm) {
    const id = lm[1];
    s = displayParty(id, partyDisplayNames) + s.slice(id.length);
  }
  s = s.replace(/(\d+)\s*[x×]\s*([a-z0-9_]+)/gi, (_, q: string, mid: string) => `${q}× ${displayMaterial(mid)}`);
  s = s.replace(/→\s*([a-z0-9_]+)/g, (_, mid: string) => `→ ${displayMaterial(mid)}`);
  return s;
}

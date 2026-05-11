"use client";

import { useMemo, useRef } from "react";

import { computeStarterHintPlotIds, starterHintCap } from "./mapStarterHints";

export type MapPlotDto = {
  id: string;
  x: number;
  y: number;
  terrain: string;
  owner: string | null;
  surveyed: boolean;
  subsurface?: Record<string, number>;
};

function plotVisualSignature(plots: readonly MapPlotDto[]): string {
  if (!plots.length) return "";
  const parts: string[] = new Array(plots.length);
  for (let i = 0; i < plots.length; i++) {
    const p = plots[i]!;
    parts[i] = `${p.id}\x00${p.owner ?? ""}\x00${p.surveyed ? 1 : 0}\x00${p.terrain}`;
  }
  return parts.join("\x01");
}

/** Keeps the same plot array reference when terrain/owner/surveyed are unchanged (avoids full map layer remounts each tick). */
export function useStablePlotsForMap(plots: MapPlotDto[] | undefined): MapPlotDto[] {
  const ref = useRef<{ sig: string; plots: MapPlotDto[] }>({ sig: "__init__", plots: [] });
  return useMemo(() => {
    if (!plots?.length) {
      ref.current = { sig: "", plots: [] };
      return ref.current.plots;
    }
    const sig = plotVisualSignature(plots);
    if (ref.current.sig === sig) return ref.current.plots;
    ref.current = { sig, plots };
    return plots;
  }, [plots]);
}

type PlotBuildingRow = { plot_id: string; party?: string };

export function useStableBuildsByPlot(
  rows: readonly PlotBuildingRow[] | undefined,
  mineOnly: boolean,
): Map<string, number> {
  const ref = useRef<{ key: string; map: Map<string, number> }>({ key: "__init__", map: new Map() });
  return useMemo(() => {
    const list = rows ?? [];
    const m = new Map<string, number>();
    for (const b of list) {
      if (mineOnly && b.party !== "player") continue;
      const id = b.plot_id;
      m.set(id, (m.get(id) ?? 0) + 1);
    }
    const key = Array.from(m.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([k, v]) => `${k}:${v}`)
      .join("|");
    if (ref.current.key === key) return ref.current.map;
    ref.current = { key, map: m };
    return m;
  }, [rows, mineOnly]);
}

type ActiveProductionRow = { plot_id: string; party?: string };

export function useStableProductionByPlot(
  rows: readonly ActiveProductionRow[] | undefined,
  mineOnly: boolean,
): Map<string, number> {
  const ref = useRef<{ key: string; map: Map<string, number> }>({ key: "__init__", map: new Map() });
  return useMemo(() => {
    const list = rows ?? [];
    const m = new Map<string, number>();
    for (const a of list) {
      if (mineOnly && a.party !== "player") continue;
      const id = a.plot_id;
      m.set(id, (m.get(id) ?? 0) + 1);
    }
    const key = Array.from(m.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([k, v]) => `${k}:${v}`)
      .join("|");
    if (ref.current.key === key) return ref.current.map;
    ref.current = { key, map: m };
    return m;
  }, [rows, mineOnly]);
}

const EMPTY_PULSE = new Set<string>();

export function useStableStarterPulseIds(
  plotsStable: readonly MapPlotDto[],
  playerOwnsLand: boolean,
): ReadonlySet<string> {
  const ref = useRef<{ key: string; set: ReadonlySet<string> }>({ key: "__init__", set: EMPTY_PULSE });
  return useMemo(() => {
    if (!plotsStable.length || playerOwnsLand) {
      const key = playerOwnsLand ? "pulse:owned" : "pulse:none";
      if (ref.current.key === key) return ref.current.set;
      ref.current = { key, set: EMPTY_PULSE };
      return EMPTY_PULSE;
    }
    const ids = computeStarterHintPlotIds(Array.from(plotsStable), starterHintCap(plotsStable.length));
    const key = `pulse:${Array.from(ids).sort().join(",")}`;
    if (ref.current.key === key) return ref.current.set;
    const set = new Set(ids);
    ref.current = { key, set };
    return set;
  }, [plotsStable, playerOwnsLand]);
}

"use client";

import { useId, useMemo } from "react";

import type { OrganicMesh } from "./mapOrganicMesh";

type PlotDto = {
  id: string;
  x: number;
  y: number;
};

export type ShipmentOverlayDto = {
  id?: string;
  shipment_id?: string;
  from_plot_id?: string | null;
  dest_plot_id: string;
};

type Props = {
  mesh: OrganicMesh;
  plots: PlotDto[];
  shipments: ShipmentOverlayDto[];
  cellPx: number;
};

/**
 * Non-interactive SVG layer: dashed arcs between origin and destination plots for in-transit goods.
 * Sits above terrain fills, below claim/build glyphs (see z-index in CSS).
 */
export function RealmMapShipmentsOverlay({ mesh, plots, shipments, cellPx }: Props) {
  const filterUid = useId().replace(/:/g, "");
  const filterId = `realm-ship-glow-${filterUid}`;
  const plotGrid = useMemo(() => {
    const m = new Map<string, { x: number; y: number }>();
    for (const p of plots) m.set(p.id, { x: p.x, y: p.y });
    return m;
  }, [plots]);

  const strokeW = Math.max(1.2, cellPx * 0.06);
  const dash = `${Math.round(cellPx * 0.22)} ${Math.round(cellPx * 0.14)}`;

  const segments = useMemo(() => {
    const out: {
      key: string;
      d: string;
      mx: number;
      my: number;
    }[] = [];
    for (let i = 0; i < shipments.length; i++) {
      const s = shipments[i]!;
      const fromId = s.from_plot_id;
      if (!fromId) continue;
      const a = plotGrid.get(fromId);
      const b = plotGrid.get(s.dest_plot_id);
      if (!a || !b) continue;
      const c1 = mesh.plotCentroid(a.x, a.y);
      const c2 = mesh.plotCentroid(b.x, b.y);
      const mx = (c1.x + c2.x) / 2;
      const my = (c1.y + c2.y) / 2 - Math.abs(c2.x - c1.x) * 0.08 - Math.abs(c2.y - c1.y) * 0.05;
      const d = `M ${c1.x} ${c1.y} Q ${mx} ${my} ${c2.x} ${c2.y}`;
      const key = s.id ?? s.shipment_id ?? `ship-${i}-${fromId}-${s.dest_plot_id}`;
      out.push({ key, d, mx, my });
    }
    return out;
  }, [mesh, plotGrid, shipments]);

  if (segments.length === 0) return null;

  const dotR = Math.max(3, cellPx * 0.07);

  return (
    <svg
      className="realm-map-shipments-overlay"
      width={mesh.contentWidth}
      height={mesh.contentHeight}
      role="presentation"
      aria-hidden
    >
      <defs>
        <filter id={filterId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="1.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <g className="realm-map-shipments-overlay__rays" filter={`url(#${filterId})`}>
        {segments.map(({ key, d, mx, my }) => (
          <g key={key}>
            <path
              className="realm-map-shipments-overlay__path"
              d={d}
              fill="none"
              strokeWidth={strokeW}
              strokeDasharray={dash}
            />
            <circle className="realm-map-shipments-overlay__dot" cx={mx} cy={my} r={dotR} />
          </g>
        ))}
      </g>
    </svg>
  );
}

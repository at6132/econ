"use client";

import type { CSSProperties } from "react";

import { ownerAccentColor, ownerTint, partyMapBadge } from "./mapHash";
import type { OrganicMesh } from "./mapOrganicMesh";

type PlotDto = {
  id: string;
  x: number;
  y: number;
  terrain: string;
  owner: string | null;
  surveyed: boolean;
};

const TERRAIN_FILL: Record<string, string> = {
  plains: "url(#realm-g-plains)",
  forest: "url(#realm-g-forest)",
  mountain: "url(#realm-g-mountain)",
  desert: "url(#realm-g-desert)",
  tundra: "url(#realm-g-tundra)",
  swamp: "url(#realm-g-swamp)",
  water_shallow: "url(#realm-g-water-shallow)",
  water_deep: "url(#realm-g-water-deep)",
};

function terrainFill(terrain: string): string {
  return TERRAIN_FILL[terrain] ?? "url(#realm-g-unknown)";
}

type Props = {
  mesh: OrganicMesh;
  plots: PlotDto[];
  selectedPlotId: string | null;
  buildsByPlot: Map<string, number>;
  /** Plot tile size in px — scales build / anchor glyphs for large “street level” maps. */
  cellPx: number;
  /** Count of active production runs per plot (any party). */
  productionByPlot: Map<string, number>;
  busy: boolean;
  mapNavSuppress: React.MutableRefObject<boolean>;
  onPlotClick: (p: PlotDto) => void;
  /** Soft pulse on these plot ids (e.g. suggested first claims). */
  starterPulsePlotIds: ReadonlySet<string>;
  /** Map pin for “you are here” / “start here” (centroid in SVG space). */
  mapAnchor: { cx: number; cy: number; caption: string } | null;
  /** Accessible name for the SVG map. */
  ariaLabel: string;
};

export function RealmMapMeshSvg({
  mesh,
  plots,
  selectedPlotId,
  buildsByPlot,
  cellPx,
  productionByPlot,
  busy,
  mapNavSuppress,
  onPlotClick,
  starterPulsePlotIds,
  mapAnchor,
  ariaLabel,
}: Props) {
  const buildFontPx = Math.max(12, Math.round(cellPx * 0.3));
  const buildStrokePx = Math.max(3, Math.round(cellPx * 0.09));
  const anchorRadius = Math.max(5, Math.round(cellPx * 0.11));
  const anchorCaptionPx = Math.max(10, Math.round(cellPx * 0.18));
  const claimFs = Math.max(9, Math.round(cellPx * 0.21));
  const claimStroke = Math.max(2, Math.round(cellPx * 0.055));
  const prodFs = Math.max(8, Math.round(cellPx * 0.2));
  const prodStroke = Math.max(2, Math.round(cellPx * 0.05));
  const anchorCaptionDy = Math.max(12, Math.round(cellPx * 0.36));
  const ordered = [...plots].sort((a, b) => {
    const as = a.id === selectedPlotId ? 1 : 0;
    const bs = b.id === selectedPlotId ? 1 : 0;
    if (as !== bs) return as - bs;
    return a.y - b.y || a.x - b.x;
  });

  return (
    <svg
      className="realm-map-mesh-svg"
      width={mesh.contentWidth}
      height={mesh.contentHeight}
      role="img"
      aria-label={ariaLabel}
    >
      <defs>
        <linearGradient id="realm-g-plains" x1="0%" y1="0%" x2="100%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#8fd060" />
          <stop offset="55%" stopColor="#4a8a38" />
          <stop offset="100%" stopColor="#356028" />
        </linearGradient>
        <linearGradient id="realm-g-forest" x1="0%" y1="0%" x2="50%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#2d8040" />
          <stop offset="100%" stopColor="#143018" />
        </linearGradient>
        <linearGradient id="realm-g-mountain" x1="0%" y1="0%" x2="100%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#c8c8d4" />
          <stop offset="45%" stopColor="#4a4a58" />
          <stop offset="100%" stopColor="#2a2a32" />
        </linearGradient>
        <linearGradient id="realm-g-desert" x1="0%" y1="0%" x2="0%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#f0d878" />
          <stop offset="100%" stopColor="#c89838" />
        </linearGradient>
        <linearGradient id="realm-g-tundra" x1="0%" y1="0%" x2="0%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#d8f0ff" />
          <stop offset="55%" stopColor="#78a8c8" />
          <stop offset="100%" stopColor="#406080" />
        </linearGradient>
        <linearGradient id="realm-g-swamp" x1="0%" y1="0%" x2="100%" y2="80%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#4a9850" />
          <stop offset="100%" stopColor="#1a4020" />
        </linearGradient>
        <linearGradient id="realm-g-water-shallow" x1="0%" y1="0%" x2="0%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#58b0e8" />
          <stop offset="100%" stopColor="#2868a8" />
        </linearGradient>
        <linearGradient id="realm-g-water-deep" x1="0%" y1="0%" x2="0%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#3068a8" />
          <stop offset="100%" stopColor="#0a1838" />
        </linearGradient>
        <linearGradient id="realm-g-unknown" x1="0%" y1="0%" x2="100%" y2="100%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#4a5260" />
          <stop offset="100%" stopColor="#2a3038" />
        </linearGradient>
      </defs>
      <g className="realm-map-mesh-regions">
        {ordered.map((p) => {
          const d = mesh.plotPath(p.x, p.y);
          const c = mesh.plotCentroid(p.x, p.y);
          const mine = p.owner === "player";
          const nBuild = buildsByPlot.get(p.id) ?? 0;
          const tint = ownerTint(p.owner);
          const isSelected = p.id === selectedPlotId;
          const cls = [
            "realm-map-region",
            mine ? "realm-map-region--mine" : "",
            p.owner && !mine ? "realm-map-region--foreign" : "",
            p.surveyed ? "realm-map-region--surveyed" : "",
            isSelected ? "realm-map-region--selected" : "",
          ]
            .filter(Boolean)
            .join(" ");
          const groupStyle: CSSProperties | undefined = p.owner ? { ["--owner-tint" as string]: tint } : undefined;
          const nProd = productionByPlot.get(p.id) ?? 0;
          const pathStroke: CSSProperties =
            p.owner && !mine && !isSelected
              ? {
                  stroke: ownerAccentColor(p.owner),
                  strokeWidth: Math.max(1.4, cellPx * 0.042),
                  strokeOpacity: 0.58,
                }
              : {};
          const buildY = nBuild > 0 ? c.y + (p.owner ? cellPx * 0.1 : 0) : c.y;
          const claimY = p.owner ? c.y - (nBuild > 0 ? cellPx * 0.34 : cellPx * 0.22) : c.y;
          const prodY =
            nProd > 0 ? c.y + (nBuild > 0 ? cellPx * 0.42 : p.owner ? cellPx * 0.3 : cellPx * 0.28) : c.y;
          return (
            <g key={p.id} className="realm-map-region-group" style={groupStyle}>
              <path
                className={`${cls}${busy ? " realm-map-region--busy" : ""}`}
                d={d}
                data-owner={p.owner ?? ""}
                fill={terrainFill(p.terrain)}
                style={pathStroke}
                focusable={false}
                onClick={() => {
                  if (busy) return;
                  if (mapNavSuppress.current) {
                    mapNavSuppress.current = false;
                    return;
                  }
                  onPlotClick(p);
                }}
              >
                <title>
                  {p.id} · {p.terrain} · owner {p.owner ?? "none"} · surveyed {p.surveyed ? "yes" : "no"}
                </title>
              </path>
              {p.owner ? <path className="realm-map-region__tint" d={d} fill="var(--owner-tint, transparent)" aria-hidden /> : null}
              {p.owner ? (
                <text
                  className="realm-map-region__claim-badge"
                  x={c.x}
                  y={claimY}
                  textAnchor="middle"
                  dominantBaseline="central"
                  aria-hidden
                  style={{
                    fontSize: claimFs,
                    strokeWidth: claimStroke,
                    fill: ownerAccentColor(p.owner),
                  }}
                >
                  {partyMapBadge(p.owner)}
                </text>
              ) : null}
              {nBuild > 0 ? (
                <text
                  className="realm-map-region__build"
                  x={c.x}
                  y={buildY}
                  textAnchor="middle"
                  dominantBaseline="central"
                  aria-hidden
                  style={{ fontSize: buildFontPx, strokeWidth: buildStrokePx }}
                >
                  {nBuild > 1 ? `▣${nBuild}` : "▣"}
                </text>
              ) : null}
              {nProd > 0 ? (
                <text
                  className="realm-map-region__prod-badge"
                  x={c.x}
                  y={prodY}
                  textAnchor="middle"
                  dominantBaseline="central"
                  aria-hidden
                  style={{ fontSize: prodFs, strokeWidth: prodStroke }}
                >
                  {nProd > 1 ? `\u2699${nProd}` : "\u2699"}
                </text>
              ) : null}
            </g>
          );
        })}
      </g>
      {starterPulsePlotIds.size > 0
        ? plots
            .filter((p) => starterPulsePlotIds.has(p.id))
            .map((p) => (
              <path
                key={`starter-${p.id}`}
                className="realm-map-starter-pulse"
                d={mesh.plotPath(p.x, p.y)}
                focusable={false}
                aria-hidden
              />
            ))
        : null}
      {mapAnchor ? (
        <g className="realm-map-anchor" pointerEvents="none" aria-hidden>
          <circle
            className="realm-map-anchor__dot"
            cx={mapAnchor.cx}
            cy={mapAnchor.cy}
            r={anchorRadius}
            style={{ strokeWidth: Math.max(2, Math.round(cellPx * 0.05)) }}
          />
          <text
            className="realm-map-anchor__caption"
            x={mapAnchor.cx}
            y={mapAnchor.cy - anchorCaptionDy}
            textAnchor="middle"
            style={{
              fontSize: anchorCaptionPx,
              strokeWidth: Math.max(2, Math.round(cellPx * 0.07)),
            }}
          >
            {mapAnchor.caption}
          </text>
        </g>
      ) : null}
    </svg>
  );
}

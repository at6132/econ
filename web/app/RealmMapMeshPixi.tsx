"use client";

import type { Application } from "pixi.js";
import { memo, useEffect, useRef } from "react";

import { ownerAccentPixi, ownerTintPixi, partyMapBadge } from "./mapHash";
import type { OrganicMesh } from "./mapOrganicMesh";

type PlotDto = {
  id: string;
  x: number;
  y: number;
  terrain: string;
  owner: string | null;
  surveyed: boolean;
};

export type MapRenderStyle = "terrain" | "satellite" | "political";

const TERRAIN_COLOR: Record<string, number> = {
  plains: 0x4a8a38,
  forest: 0x1f5028,
  mountain: 0x4a4a58,
  desert: 0xc89838,
  tundra: 0x78a8c8,
  swamp: 0x2a6030,
  water_shallow: 0x2868a8,
  water_deep: 0x0a1838,
  unknown: 0x3a4048,
};

function scaleRgb(hex: number, m: number): number {
  const r = Math.min(255, Math.round(((hex >> 16) & 0xff) * m));
  const g = Math.min(255, Math.round(((hex >> 8) & 0xff) * m));
  const b = Math.min(255, Math.round((hex & 0xff) * m));
  return (r << 16) | (g << 8) | b;
}

function terrainFill(terrain: string, mapStyle: MapRenderStyle): number {
  const base = TERRAIN_COLOR[terrain] ?? TERRAIN_COLOR.unknown;
  if (mapStyle === "satellite") return scaleRgb(base, 0.88);
  return base;
}

function lightenRgb(hex: number, factor: number): number {
  const r = Math.min(255, Math.round(((hex >> 16) & 0xff) * factor));
  const g = Math.min(255, Math.round(((hex >> 8) & 0xff) * factor));
  const b = Math.min(255, Math.round((hex & 0xff) * factor));
  return (r << 16) | (g << 8) | b;
}

type Props = {
  mesh: OrganicMesh;
  plots: PlotDto[];
  selectedPlotId: string | null;
  buildsByPlot: Map<string, number>;
  /** Plot tile size in px — scales build / anchor labels for large maps. */
  cellPx: number;
  /** Active production runs per plot (any party). */
  productionByPlot: Map<string, number>;
  busy: boolean;
  mapNavSuppress: React.MutableRefObject<boolean>;
  onPlotClick: (p: PlotDto) => void;
  starterPulsePlotIds: ReadonlySet<string>;
  mapAnchor: { cx: number; cy: number; caption: string } | null;
  ariaLabel: string;
  mapStyle: MapRenderStyle;
  logisticsScope: "all" | "mine";
};

export const RealmMapMeshPixi = memo(function RealmMapMeshPixi(props: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let cancelled = false;
    let application: Application | null = null;

    void (async () => {
      try {
        const { Application: App, Container, Graphics, Text, TextStyle } = await import("pixi.js");
        const pr = propsRef.current;
        const app = new App();
        await app.init({
          width: pr.mesh.contentWidth,
          height: pr.mesh.contentHeight,
          backgroundAlpha: 0,
          antialias: false,
          resolution: typeof window !== "undefined" ? Math.min(window.devicePixelRatio || 1, 2) : 1,
          autoDensity: true,
        });

        if (cancelled) {
          app.destroy(true);
          return;
        }

        application = app;
        host.replaceChildren(app.canvas);
        app.canvas.className = "realm-map-mesh-pixi__canvas";
        app.canvas.setAttribute("role", "img");
        app.canvas.setAttribute("aria-label", pr.ariaLabel);

        const root = new Container();
        app.stage.addChild(root);

        const {
          mesh,
          plots,
          selectedPlotId,
          buildsByPlot,
          cellPx,
          productionByPlot,
          busy,
          mapStyle,
          mapAnchor,
          starterPulsePlotIds,
          logisticsScope,
        } = pr;

        const ordered = [...plots].sort((a, b) => {
          const as = a.id === selectedPlotId ? 1 : 0;
          const bs = b.id === selectedPlotId ? 1 : 0;
          if (as !== bs) return as - bs;
          return a.y - b.y || a.x - b.x;
        });

        for (const p of ordered) {
          const poly = mesh.plotPolygon(p.x, p.y);
          const flat = [poly[0].x, poly[0].y, poly[1].x, poly[1].y, poly[2].x, poly[2].y, poly[3].x, poly[3].y];

          const g = new Graphics();
          let fillHex = terrainFill(p.terrain, mapStyle);
          if (p.surveyed) fillHex = lightenRgb(fillHex, 1.05);

          g.poly(flat, true).fill({ color: fillHex });
          const tint = ownerTintPixi(p.owner);
          if (tint) {
            g.poly(flat, true).fill({ color: tint.color, alpha: tint.alpha });
          }

          const isSel = p.id === selectedPlotId;
          const mine = p.owner === "player";
          const foreign = Boolean(p.owner && !mine);
          let strokeW = 1;
          let strokeCol = 0x000000;
          let strokeAlpha = 0.38;

          if (isSel) {
            strokeCol = 0xffd84a;
            strokeAlpha = 1;
            strokeW = 3.5;
          } else if (mine) {
            if (mapStyle === "political") {
              strokeCol = 0xffd84a;
              strokeAlpha = 0.55;
              strokeW = 1.5;
            } else {
              strokeCol = 0x6ee7ff;
              strokeAlpha = 0.5;
              strokeW = 1.5;
            }
          } else if (foreign && logisticsScope === "all") {
            strokeCol = ownerAccentPixi(p.owner!);
            strokeW = Math.max(1.25, cellPx * 0.045);
            strokeAlpha = mapStyle === "political" ? 0.68 : 0.5;
          }

          g.poly(flat, true).stroke({ width: strokeW, color: strokeCol, alpha: strokeAlpha, join: "round" });

          if (busy) {
            g.alpha = 0.52;
            g.eventMode = "none";
          } else {
            g.eventMode = "static";
            g.cursor = "pointer";
            g.on("pointertap", () => {
              const { onPlotClick, mapNavSuppress } = propsRef.current;
              if (mapNavSuppress.current) {
                mapNavSuppress.current = false;
                return;
              }
              onPlotClick(p);
            });
          }

          root.addChild(g);
        }

        const buildFs = Math.max(12, Math.round(cellPx * 0.32));
        const buildStrokeW = Math.max(3, Math.round(cellPx * 0.1));
        const buildStyle = new TextStyle({
          fontFamily: "VT323, ui-monospace, monospace",
          fontSize: buildFs,
          fill: 0xffd84a,
          stroke: { color: 0x000000, width: buildStrokeW },
        });

        const claimFs = Math.max(9, Math.round(cellPx * 0.21));
        const claimStrokeW = Math.max(2, Math.round(cellPx * 0.055));
        const prodFs = Math.max(8, Math.round(cellPx * 0.2));
        const prodStrokeW = Math.max(2, Math.round(cellPx * 0.05));

        for (const p of ordered) {
          if (!p.owner) continue;
          if (logisticsScope === "mine" && p.owner !== "player") continue;
          const c = mesh.plotCentroid(p.x, p.y);
          const nBuild = buildsByPlot.get(p.id) ?? 0;
          const claimY = c.y - (nBuild > 0 ? cellPx * 0.34 : cellPx * 0.22);
          const label = partyMapBadge(p.owner);
          const t = new Text({
            text: label,
            style: new TextStyle({
              fontFamily: "VT323, ui-monospace, monospace",
              fontSize: claimFs,
              fill: ownerAccentPixi(p.owner),
              stroke: { color: 0x000000, width: claimStrokeW },
            }),
          });
          t.anchor.set(0.5, 0.5);
          t.x = c.x;
          t.y = claimY;
          t.eventMode = "none";
          root.addChild(t);
        }

        for (const p of ordered) {
          const nBuild = buildsByPlot.get(p.id) ?? 0;
          if (nBuild < 1) continue;
          const c = mesh.plotCentroid(p.x, p.y);
          const label = nBuild > 1 ? `\u25a3${nBuild}` : "\u25a3";
          const t = new Text({ text: label, style: buildStyle });
          t.anchor.set(0.5, 0.5);
          t.x = c.x;
          t.y = c.y + (p.owner ? cellPx * 0.1 : 0);
          t.eventMode = "none";
          root.addChild(t);
        }

        for (const p of ordered) {
          const nProd = productionByPlot.get(p.id) ?? 0;
          if (nProd < 1) continue;
          const c = mesh.plotCentroid(p.x, p.y);
          const nBuild = buildsByPlot.get(p.id) ?? 0;
          const prodY = c.y + (nBuild > 0 ? cellPx * 0.42 : p.owner ? cellPx * 0.3 : cellPx * 0.28);
          const label = nProd > 1 ? `\u2699${nProd}` : "\u2699";
          const t = new Text({
            text: label,
            style: new TextStyle({
              fontFamily: "VT323, ui-monospace, monospace",
              fontSize: prodFs,
              fill: 0x7dd3fc,
              stroke: { color: 0x000000, width: prodStrokeW },
            }),
          });
          t.anchor.set(0.5, 0.5);
          t.x = c.x;
          t.y = prodY;
          t.eventMode = "none";
          root.addChild(t);
        }

        for (const p of plots) {
          if (!starterPulsePlotIds.has(p.id)) continue;
          const poly = mesh.plotPolygon(p.x, p.y);
          const flat = [poly[0].x, poly[0].y, poly[1].x, poly[1].y, poly[2].x, poly[2].y, poly[3].x, poly[3].y];
          const sp = new Graphics();
          sp.poly(flat, true)
            .fill({ color: 0xffd84a, alpha: 0.11 })
            .stroke({ width: 1.5, color: 0xffd84a, alpha: 0.42, join: "round" });
          sp.eventMode = "none";
          root.addChild(sp);
        }

        if (mapAnchor) {
          const { cx, cy, caption } = mapAnchor;
          const dot = new Graphics();
          const dotR = Math.max(5, Math.round(cellPx * 0.11));
          dot.circle(cx, cy, dotR).fill({ color: 0xffd84a }).stroke({ width: 2, color: 0x000000, alpha: 1 });
          dot.eventMode = "none";
          root.addChild(dot);

          const capFs = Math.max(12, Math.round(cellPx * 0.2));
          const capDy = Math.max(14, Math.round(cellPx * 0.38));
          const cap = new Text({
            text: caption,
            style: new TextStyle({
              fontFamily: "VT323, ui-monospace, monospace",
              fontSize: capFs,
              fill: 0xf4ead8,
              stroke: { color: 0x000000, width: Math.max(2, Math.round(cellPx * 0.06)) },
            }),
          });
          cap.anchor.set(0.5, 1);
          cap.x = cx;
          cap.y = cy - capDy;
          cap.eventMode = "none";
          root.addChild(cap);
        }
      } catch {
        /* Pixi init can fail on very old browsers — leave host empty */
      }
    })();

    return () => {
      cancelled = true;
      if (application) {
        application.destroy(true);
        application = null;
      }
    };
  }, [
    props.mesh,
    props.plots,
    props.selectedPlotId,
    props.buildsByPlot,
    props.productionByPlot,
    props.cellPx,
    props.busy,
    props.mapStyle,
    props.logisticsScope,
    props.mapAnchor,
    props.starterPulsePlotIds,
    props.ariaLabel,
  ]);

  return <div ref={hostRef} className="realm-map-mesh-pixi" />;
});

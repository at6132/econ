import { hash32 } from "./mapHash";

export type OrganicMesh = {
  readonly cellPx: number;
  readonly pad: number;
  readonly contentWidth: number;
  readonly contentHeight: number;
  /** Quad corners in winding order for SVG path / canvas / Pixi. */
  plotPolygon: (gx: number, gy: number) => readonly [{ x: number; y: number }, { x: number; y: number }, { x: number; y: number }, { x: number; y: number }];
  plotPath: (gx: number, gy: number) => string;
  plotCentroid: (gx: number, gy: number) => { x: number; y: number };
};

function fmt(n: number): string {
  return n.toFixed(2);
}

/** Shared vertex jitter so adjacent plots meet with no cracks (organic tiles, not a square grid). */
function vertexJitter(worldSeed: number, vx: number, vy: number, amp: number): { dx: number; dy: number } {
  const h1 = hash32(worldSeed, `vj:${vx},${vy}`);
  const h2 = hash32(worldSeed ^ 0xdeadbeef, `vj:${vx},${vy}`);
  const dx = ((h1 & 0xffff) / 65535 - 0.5) * 2 * amp;
  const dy = ((h2 & 0xffff) / 65535 - 0.5) * 2 * amp;
  return { dx, dy };
}

function corner(worldSeed: number, vx: number, vy: number, pad: number, cell: number, amp: number) {
  const { dx, dy } = vertexJitter(worldSeed, vx, vy, amp);
  return { x: pad + vx * cell + dx, y: pad + vy * cell + dy };
}

export function buildOrganicMesh(
  worldSeed: number,
  gridW: number,
  gridH: number,
  pad: number,
  cellPx: number,
): OrganicMesh {
  const amp = cellPx * 0.42;
  const plotPolygon = (gx: number, gy: number) => {
    const c00 = corner(worldSeed, gx, gy, pad, cellPx, amp);
    const c10 = corner(worldSeed, gx + 1, gy, pad, cellPx, amp);
    const c11 = corner(worldSeed, gx + 1, gy + 1, pad, cellPx, amp);
    const c01 = corner(worldSeed, gx, gy + 1, pad, cellPx, amp);
    return [c00, c10, c11, c01] as const;
  };
  const plotPath = (gx: number, gy: number) => {
    const [c00, c10, c11, c01] = plotPolygon(gx, gy);
    return `M ${fmt(c00.x)} ${fmt(c00.y)} L ${fmt(c10.x)} ${fmt(c10.y)} L ${fmt(c11.x)} ${fmt(c11.y)} L ${fmt(c01.x)} ${fmt(c01.y)} Z`;
  };
  const plotCentroid = (gx: number, gy: number) => {
    const [c00, c10, c11, c01] = plotPolygon(gx, gy);
    return { x: (c00.x + c10.x + c11.x + c01.x) / 4, y: (c00.y + c10.y + c11.y + c01.y) / 4 };
  };
  const contentWidth = pad * 2 + gridW * cellPx;
  const contentHeight = pad * 2 + gridH * cellPx;
  return { cellPx, pad, contentWidth, contentHeight, plotPolygon, plotPath, plotCentroid };
}

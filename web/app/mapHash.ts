/** Deterministic 32-bit mix for visuals (not crypto). */
export function hash32(seed: number, s: string): number {
  let h = seed ^ s.length;
  for (let i = 0; i < s.length; i++) {
    h = Math.imul(h ^ s.charCodeAt(i), 0x9e3779b1);
  }
  return h >>> 0;
}

export function cellTextureShift(plotId: string, worldSeed: number): { bx: number; by: number } {
  const h = hash32(worldSeed, plotId);
  return { bx: (h & 31) - 15, by: ((h >> 5) & 31) - 15 };
}

export function cellRoughRadius(plotId: string, worldSeed: number): number {
  const h = hash32(worldSeed, `r:${plotId}`);
  return 1 + (h % 4);
}

export function ownerTint(owner: string | null): string {
  if (!owner) return "transparent";
  const h = hash32(0xfeed, owner);
  const hue = h % 360;
  return `hsla(${hue}, 55%, 45%, 0.22)`;
}

function hslToRgbByte(h: number, s: number, l: number): { r: number; g: number; b: number } {
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h * 12) % 12;
    return l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
  };
  return {
    r: Math.round(255 * f(0)),
    g: Math.round(255 * f(8)),
    b: Math.round(255 * f(4)),
  };
}

/** Pixi overlay fill for plot owner (hue matches CSS `ownerTint`). */
export function ownerTintPixi(owner: string | null): { color: number; alpha: number } | null {
  if (!owner) return null;
  const h = hash32(0xfeed, owner);
  const hue = (h % 360) / 360;
  const { r, g, b } = hslToRgbByte(hue, 0.55, 0.45);
  const color = (r << 16) | (g << 8) | b;
  return { color, alpha: 0.26 };
}

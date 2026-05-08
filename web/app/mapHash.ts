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

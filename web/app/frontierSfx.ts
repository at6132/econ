import type { MapFxKind } from "./mapFxTypes";

let audioCtx: AudioContext | null = null;

function ctx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return null;
  try {
    audioCtx = audioCtx ?? new AudioContext();
    return audioCtx;
  } catch {
    return null;
  }
}

function beep(f: number, dur: number, type: OscillatorType = "square", gain = 0.04) {
  const c = ctx();
  if (!c) return;
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type;
  o.frequency.value = f;
  g.gain.value = gain;
  o.connect(g);
  g.connect(c.destination);
  const t = c.currentTime;
  g.gain.setValueAtTime(gain, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + dur);
  o.start(t);
  o.stop(t + dur + 0.02);
}

const KIND_PRESET: Partial<Record<MapFxKind, () => void>> = {
  claim: () => {
    beep(220, 0.08);
    beep(330, 0.1, "square", 0.035);
  },
  survey: () => {
    beep(440, 0.05);
    beep(660, 0.12, "triangle", 0.03);
  },
  build: () => {
    beep(180, 0.06);
    beep(120, 0.14, "sawtooth", 0.025);
  },
  trade: () => {
    beep(523, 0.05);
    beep(784, 0.08, "square", 0.03);
  },
  produce: () => {
    beep(350, 0.07);
    beep(280, 0.1, "triangle", 0.028);
  },
  tick: () => {
    beep(110, 0.12, "sine", 0.045);
    beep(165, 0.1, "sine", 0.03);
  },
  ship: () => {
    beep(200, 0.08);
    beep(160, 0.15, "triangle", 0.03);
  },
  hire: () => {
    beep(400, 0.06);
    beep(500, 0.1, "square", 0.028);
  },
  contract: () => {
    beep(300, 0.07);
    beep(450, 0.11, "triangle", 0.026);
  },
};

export function playFrontierSfx(kind: MapFxKind): void {
  KIND_PRESET[kind]?.();
}

/** Call after first user gesture if browser suspended AudioContext */
export function resumeFrontierAudio(): void {
  void ctx()?.resume();
}

"use client";

import { AnimatePresence, motion } from "framer-motion";

import type { MapFxEvent, MapFxKind } from "./mapFxTypes";

const KIND_CLASS: Record<MapFxKind, string> = {
  claim: "realm-map-fx-burst--claim",
  survey: "realm-map-fx-burst--survey",
  build: "realm-map-fx-burst--build",
  trade: "realm-map-fx-burst--trade",
  produce: "realm-map-fx-burst--produce",
  tick: "realm-map-fx-burst--tick",
  ship: "realm-map-fx-burst--ship",
  hire: "realm-map-fx-burst--hire",
  contract: "realm-map-fx-burst--contract",
};

const DEFAULT_LABEL: Partial<Record<MapFxKind, string>> = {
  claim: "CLAIM",
  survey: "SCAN",
  build: "BUILD",
  trade: "TRADE",
  produce: "MAKE",
  tick: "TIME",
  ship: "SHIP",
  hire: "HIRE",
  contract: "PACT",
};

const KIND_COLOR: Record<MapFxKind, string> = {
  claim: "#ffd84a",
  survey: "#6ee7ff",
  build: "#c9a227",
  trade: "#7bed9f",
  produce: "#ff9f6e",
  tick: "#e8d4ff",
  ship: "#6eb5ff",
  hire: "#d2a8ff",
  contract: "#ff8a8a",
};

type Props = {
  events: MapFxEvent[];
  width: number;
  height: number;
  getBurstCenter: (gx: number, gy: number) => { x: number; y: number };
  /** Scales ring + particle spread (≈ cell size). */
  burstScale: number;
};

function Particle({
  delay,
  angle,
  dist,
  color,
}: {
  delay: number;
  angle: number;
  dist: number;
  color: string;
}) {
  const rad = (angle * Math.PI) / 180;
  const x = Math.cos(rad) * dist;
  const y = Math.sin(rad) * dist;
  return (
    <motion.span
      className="realm-map-fx-particle"
      style={{ background: color }}
      initial={{ opacity: 1, x: 0, y: 0, scale: 1 }}
      animate={{ opacity: 0, x, y, scale: 0.2 }}
      transition={{ duration: 0.75, delay, ease: "easeOut" }}
    />
  );
}

function Burst({
  ev,
  getBurstCenter,
  burstScale,
}: {
  ev: MapFxEvent;
  getBurstCenter: (gx: number, gy: number) => { x: number; y: number };
  burstScale: number;
}) {
  const { x: cx, y: cy } = getBurstCenter(ev.gx, ev.gy);
  const label = ev.label ?? DEFAULT_LABEL[ev.kind] ?? ev.kind.toUpperCase();
  const n = 10;
  const color = KIND_COLOR[ev.kind];
  const particles = Array.from({ length: n }, (_, i) => ({
    angle: (360 / n) * i + (ev.id % 7) * 3,
    dist: burstScale * 0.85 + (i % 3) * 6,
    delay: i * 0.02,
  }));

  return (
    <motion.div
      className={`realm-map-fx-burst ${KIND_CLASS[ev.kind]}`}
      style={{ left: cx, top: cy, color }}
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      <motion.div
        className="realm-map-fx-ring"
        initial={{ scale: 0.2, opacity: 0.9 }}
        animate={{ scale: 2.2, opacity: 0 }}
        transition={{ duration: 0.65, ease: "easeOut" }}
      />
      {particles.map((p, i) => (
        <Particle key={i} angle={p.angle} dist={p.dist} delay={p.delay} color={color} />
      ))}
      {ev.kind === "build" ? (
        <motion.div
          className="realm-map-fx-scaffold"
          initial={{ scaleY: 0, opacity: 1 }}
          animate={{ scaleY: 1, opacity: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
        />
      ) : null}
      <motion.span
        className="realm-map-fx-label"
        initial={{ y: 8, opacity: 0, scale: 0.7 }}
        animate={{ y: -burstScale * 0.55, opacity: 1, scale: 1 }}
        exit={{ opacity: 0, y: -burstScale }}
        transition={{ type: "spring", stiffness: 420, damping: 22 }}
      >
        {label}
      </motion.span>
    </motion.div>
  );
}

export function RealmMapFxOverlay({ events, width, height, getBurstCenter, burstScale }: Props) {
  return (
    <div className="realm-map-fx-layer" style={{ width, height }} aria-hidden>
      <AnimatePresence>
        {events.map((ev) => (
          <Burst key={ev.id} ev={ev} getBurstCenter={getBurstCenter} burstScale={burstScale} />
        ))}
      </AnimatePresence>
    </div>
  );
}

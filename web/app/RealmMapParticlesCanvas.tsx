"use client";

import { useEffect, useRef } from "react";

export type MapSpark = {
  id: number;
  cx: number;
  cy: number;
  hue: number;
};

type Particle = { x: number; y: number; vx: number; vy: number; life: number; max: number; h: number };

type Props = {
  width: number;
  height: number;
  sparks: MapSpark[];
};

export function RealmMapParticlesCanvas({ width, height, sparks }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const rafRef = useRef<number>(0);
  const spawned = useRef<Set<number>>(new Set());

  useEffect(() => {
    for (const s of sparks) {
      if (spawned.current.has(s.id)) continue;
      spawned.current.add(s.id);
      const n = 40;
      for (let i = 0; i < n; i++) {
        const ang = (Math.PI * 2 * i) / n + (s.id % 7) * 0.12;
        const sp = 1.1 + (i % 6) * 0.28;
        particlesRef.current.push({
          x: s.cx,
          y: s.cy,
          vx: Math.cos(ang) * sp,
          vy: Math.sin(ang) * sp,
          life: 0,
          max: 26 + (i % 10),
          h: s.hue,
        });
      }
    }
  }, [sparks]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = typeof window !== "undefined" ? Math.min(2, window.devicePixelRatio || 1) : 1;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const c2d = canvas.getContext("2d");
    if (!c2d) return;

    const tick = () => {
      c2d.setTransform(dpr, 0, 0, dpr, 0, 0);
      c2d.clearRect(0, 0, width, height);
      const next: Particle[] = [];
      for (const p of particlesRef.current) {
        p.life += 1;
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.07;
        const t = 1 - p.life / p.max;
        if (t > 0) {
          c2d.fillStyle = `hsla(${p.h}, 88%, 62%, ${0.2 + t * 0.75})`;
          const sz = 1.5 + t * 2.5;
          c2d.fillRect(p.x - sz / 2, p.y - sz / 2, sz, sz);
          next.push(p);
        }
      }
      particlesRef.current = next;
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [width, height]);

  if (width < 1 || height < 1) return null;
  return <canvas ref={canvasRef} className="realm-map-particles-canvas" aria-hidden />;
}

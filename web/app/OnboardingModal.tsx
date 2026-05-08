"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useState } from "react";

const STEPS = [
  {
    title: "You just landed",
    body: "This grid is the continent. Empty plots are yours to claim. AI parties already list grain, timber, coal, and clay — the economy is waking up.",
  },
  {
    title: "Claim → survey → build",
    body: "Click an empty cell to claim it. Click again on your plot to survey ($500) and reveal subsurface hints. Select a surveyed plot to run recipes or place stub buildings.",
  },
  {
    title: "Time is the engine",
    body: "Advance tick runs transit, production, and NPC loops. Watch the action log and market depth chart — best ask prices are snapshotted every tick.",
  },
  {
    title: "Trade, hire, save",
    body: "Use the Market tab for the order book. Logistics covers shipping and inventory. Contracts tab has hire bonuses (employment stubs) and supply contracts. Save your SQLite snapshot when you are done.",
  },
];

type Props = {
  open: boolean;
  onComplete: () => void;
};

export function OnboardingModal({ open, onComplete }: Props) {
  const [step, setStep] = useState(0);

  const finish = useCallback(() => {
    try {
      localStorage.setItem("realm_frontier_onboard_v2", "1");
    } catch {
      /* ignore */
    }
    setStep(0);
    onComplete();
  }, [onComplete]);

  const next = () => {
    if (step >= STEPS.length - 1) finish();
    else setStep((s) => s + 1);
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          key="backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="onboard-title"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
            background: "rgba(5, 8, 12, 0.72)",
            backdropFilter: "blur(8px)",
          }}
        >
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 380, damping: 28 }}
            style={{
              width: "min(440px, 100%)",
              borderRadius: 20,
              padding: "28px 28px 22px",
              background: "linear-gradient(165deg, var(--realm-panel) 0%, var(--realm-panel-deep) 100%)",
              border: "1px solid var(--realm-border)",
              boxShadow: "var(--realm-glow), 0 24px 80px rgba(0,0,0,0.45)",
            }}
          >
            <div
              style={{
                fontSize: 11,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--realm-muted)",
                marginBottom: 8,
              }}
            >
              Frontier briefing · step {step + 1} of {STEPS.length}
            </div>
            <h2 id="onboard-title" style={{ margin: "0 0 12px", fontSize: 22, fontWeight: 650, letterSpacing: "-0.02em" }}>
              {STEPS[step].title}
            </h2>
            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: "var(--realm-dim)" }}>{STEPS[step].body}</p>
            <div
              style={{
                display: "flex",
                gap: 10,
                marginTop: 24,
                flexWrap: "wrap",
                justifyContent: "flex-end",
              }}
            >
              <button type="button" className="realm-btn realm-btn--ghost" onClick={finish}>
                Skip all
              </button>
              <button type="button" className="realm-btn realm-btn--primary" onClick={next}>
                {step >= STEPS.length - 1 ? "Enter the world" : "Next"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

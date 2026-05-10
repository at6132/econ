"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useState } from "react";

import { FRONTIER_ONBOARD_STORAGE_KEY } from "./frontierConstants";

const STEPS = [
  {
    title: "New game",
    body: "This is Frontier — a solo slice of Realm. The map is your overworld: empty tiles are unclaimed frontier. Rivals already post grain and timber on the market.",
  },
  {
    title: "Claim, survey, build",
    body: "Click an empty tile to claim it. Click your land again to survey (costs cash) and reveal subsurface hints. On a surveyed plot you queue recipes and drop placeholder buildings.",
  },
  {
    title: "You control time",
    body: "Nothing simulates in the background. Hit End turn when you are ready — transit, production timers, and NPC ticks all resolve on your command.",
  },
  {
    title: "Menus = depth",
    body: "Use the left Atlas-style menu: Bazaar for orders, Caravans for shipping, Pacts for supply contracts, optional memo honor flow, and hiring, Chronicle for the log and save. Atlas lists what is live vs stub vs planned.",
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
      localStorage.setItem(FRONTIER_ONBOARD_STORAGE_KEY, "1");
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
          className="realm-onboard-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            className="realm-onboard-card"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ type: "spring", stiffness: 420, damping: 28 }}
          >
            <div className="realm-onboard-kicker">
              Player manual · page {step + 1} / {STEPS.length}
            </div>
            <h2 id="onboard-title" className="realm-onboard-title">
              {STEPS[step].title}
            </h2>
            <p className="realm-onboard-body">{STEPS[step].body}</p>
            <div className="realm-onboard-actions">
              <button type="button" className="realm-btn realm-btn--ghost" onClick={finish}>
                Skip
              </button>
              <button type="button" className="realm-btn realm-btn--primary" onClick={next}>
                {step >= STEPS.length - 1 ? "Play" : "Next"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

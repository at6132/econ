"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useState } from "react";

import { FRONTIER_ONBOARD_STORAGE_KEY } from "./frontierConstants";

const STEPS = [
  {
    title: "What you are looking at",
    body: `Realm is an economic civilization sim: land, materials, work, money, and contracts — no quest chain, no boss fight, no win screen. Frontier is the solo Phase 1 client wired to the real Python engine.

The map and the command panel are the whole game right now. Chronicle is the paper trail when a balance or inventory move surprises you.`,
  },
  {
    title: "Map: claim land",
    body: `Click a region to select it — the gold outline follows that plot's shape. Unclaimed land: open Territory & works and press Claim (free in this build). Your unsurveyed plots: Survey from the panel for the listed cash fee, then build and produce.

Pan by dragging, zoom with the scroll wheel. The style toggle is cosmetic (terrain / satellite / political).

You start with cash and starter stock. Scripted traders already post on the book so the economy is not empty on load.`,
  },
  {
    title: "Territory: survey, build, produce",
    body: `In Territory & works, your selected plot shows terrain, owner, survey status, and any structures. After you survey, subsurface grades appear there.

Building spends cash and attaches a structure. Field stockade raises party-wide storage headroom. Tool cache and watch hut reduce recipe labor cash on that plot only.

Produce queues a recipe: inputs and labor cash leave up front; outputs land when the run finishes. If you are at the storage cap, the run waits — nothing is silently deleted.`,
  },
  {
    title: "Time: the clock runs",
    body: `The engine advances in discrete ticks, but the client runs them for you on a timer. Use Pause when you want to read or stack orders without the world moving. The speed control changes how fast real time maps to ticks — it is solo pacing only, not a lore clock.

Each tick walks transit, production, spoilage where applicable, wages, scripted NPC trading, and contract deadlines.`,
  },
  {
    title: "Bazaar: book and P2P",
    body: `Limit ask: quote a price and park inventory until fill or cancel. Limit bid: lock cash in market escrow up to your max price.

Resting orders can cross when prices meet. You can also lift the book with aggressive flow or sell into bids. P2P is one atomic swap with a named counterparty.

Optional controls: iceberg clips hide part of displayed size; minimum “honored” counts let you refuse matches with counterparties you do not trust yet. Full storage blocks incoming deliveries.`,
  },
  {
    title: "Caravans",
    body: `Ship between plots you control (where the rules allow). You pay a distance-based fee up front; cargo is in transit until the arrival tick.

Watch the in-transit list so you do not double-spend inventory. If the destination cannot take goods, the engine blocks the move.`,
  },
  {
    title: "Pacts",
    body: `Supply contracts: propose, buyer accepts, supplier fulfills by the due tick with goods and payment. Miss the deadline and the supplier takes a breach mark on reputation; terms can hold a buyer deposit or liquidated damages.

Memo contracts are lightweight — reputation counters only, no physical delivery.`,
  },
  {
    title: "Hiring",
    body: `Hire pays a signing bonus and records employment. You can add a recurring wage every N ticks.

When you run production, part of the recipe labor cash routes to signed hires (split evenly among them). If you are broke, wages simply do not move.`,
  },
  {
    title: "Chronicle and saves",
    body: `Chronicle streams engine events: trades, production, breaches, hires. Save writes a SQLite snapshot the engine can reload. Dev reset rebuilds the bootstrap world from seed and drops unsaved play.

Replay manual in the header reopens this text; it also clears saved pause/speed so you land back on the default running clock.`,
  },
  {
    title: "First session",
    body: `1) Claim a plot. 2) Survey when you can. 3) Let a few ticks pass and watch the book and NPCs. 4) Run one production chain or place one limit order. 5) Ship something or sign a small supply deal once you see how timers work.

Pick a role you like: market maker, hauler, contract-heavy, or industrial hermit. The point is the loop you build — not clearing a fixed storyline.`,
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
              Frontier manual · {step + 1} / {STEPS.length}
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
                {step >= STEPS.length - 1 ? "Done" : "Next"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

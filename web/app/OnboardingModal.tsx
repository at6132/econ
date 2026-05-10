"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useState } from "react";

import { FRONTIER_ONBOARD_STORAGE_KEY } from "./frontierConstants";

const STEPS = [
  {
    title: "Frontier, in one screen",
    body: `This is Realm: Frontier — a solo build of the economic sim. No quests, no campaign map to “finish.” You run a ledger, plots, and markets against scripted traders and the clock.

Everything important lives in the command panel (left) and the map. If you get lost, open Chronicle for the event log or replay this manual from the header.`,
  },
  {
    title: "Map: claim land",
    body: `Click a region on the map. If it has no owner, you can claim it — that tile is now yours to survey and build on.

Pan by dragging, zoom with the scroll wheel. The style toggle cycles terrain / satellite / political; it’s cosmetic only.

You start with cash and starter stock. Rivals already list goods on the market so you aren’t staring at an empty economy.`,
  },
  {
    title: "Territory: survey, build, produce",
    body: `Open Territory & works, select your plot, then Survey once you can pay the fee. Survey reveals subsurface hints (ore, clay, coal grades) for that tile.

Build spends cash and attaches a structure to the plot. Field stockade raises how much stuff you can hold party-wide. Tool cache and watch hut shave recipe labor cost on that plot only.

Produce picks a recipe: inputs and labor cash leave your balance up front; outputs arrive after a fixed number of turns. If you’re stuffed to the storage cap, production waits instead of dumping goods into the void.`,
  },
  {
    title: "You drive the clock",
    body: `The sim does not run in the background. Press End turn when you’re ready.

Each turn runs transit, production, spoilage (grain can turn into spoiled grain over time), wages for any hires you set up, NPC trading scripts, then contract deadlines. After that the tick number increments.

If something didn’t happen, you probably haven’t advanced the turn yet.`,
  },
  {
    title: "Bazaar: book + P2P",
    body: `Limit sell: you quote a price and park inventory until fill or cancel. Limit bid: you lock cash in market escrow up to your limit price.

Incoming orders can cross automatically. You can also hit the book with aggressive buy or sell-into-bids. P2P is one direct trade with a named counterparty (cash and goods swap in one shot).

Advanced (optional): iceberg clips hide part of your size on the book; minimum “honored” counts let you refuse matches with counterparties you don’t trust yet. Storage limits apply on delivery — full silos block incoming goods.`,
  },
  {
    title: "Caravans: move stuff",
    body: `Caravans ships material between two plots you control (or that the rules allow). You pay a distance-based fee up front. The shipment sits in transit and lands after a number of turns.

Check the in-transit table so you don’t double-spend the same inventory. If a delivery can’t land because storage is full, the engine blocks it.`,
  },
  {
    title: "Pacts: supply deals",
    body: `Under Pacts you can run a bilateral supply contract: propose, buyer accepts, supplier fulfills by the due tick with goods and agreed payment.

Miss the deadline and the supplier eats a breach mark on reputation; optional terms can hold a buyer deposit in escrow until fulfill, or charge liquidated damages on breach.

Memo contracts are a lighter handshake for experiments — supply deals use the dedicated flow.`,
  },
  {
    title: "Hiring and wages",
    body: `Hire pays a signing bonus from you to a listed NPC party and opens a stub employment record. You can add a recurring wage paid every N turns if you want the ledger to keep moving.

When you run production, part of the recipe’s labor cash is routed to hired workers you’ve signed — check the contract / hire panel for who counts.

No magical workers: if you’re broke, wages simply don’t move money.`,
  },
  {
    title: "Chronicle, save, reset",
    body: `Chronicle streams engine events: claims, trades, production, breaches, hires. Read it when a balance or inventory change surprises you.

Save writes a SQLite snapshot the engine can reload (path shown in the UI). Load brings that world back.

Dev: reset world rebuilds the in-memory Frontier from seed 42 and clears unsaved play. Your browser may still hold this manual’s “seen” flag — use Replay briefing in the header to reopen these pages.`,
  },
  {
    title: "How to actually start playing",
    body: `1) Claim a plot. 2) Survey it when you can afford it. 3) End turn a few times and watch the market and NPCs move. 4) Run one production batch (timber → lumber is a classic first chain) or place one limit order. 5) Ship something or sign a small supply pact when you understand the timers.

Pick a lane you enjoy: market maker, hauler, contract lawyer on the side, or hermit industrialist. The fun is making the loop yours — not clearing a scripted checklist.

When you’re ready, hit Play and go break something on purpose. That’s the test.`,
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
                {step >= STEPS.length - 1 ? "Play" : "Next"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

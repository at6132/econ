# 02 — Design Pillars

These are the seven non-negotiable principles that govern every design decision. When in doubt, return to these. When considering a new feature, ask: *does it strengthen or weaken these pillars?*

---

## Pillar 1 — Players invent the content

Designers ship rules and primitives. Players ship businesses, prices, services, currencies, alliances, scams, and stories.

**Implication:** We do not write production recipes. We do not pre-define "iron mines." We do not script tutorials with NPCs offering you swords. We do not balance "the economy" — we balance the *physics* and let the economy balance itself.

**Test:** If a feature requires us to pick categories ("here are the 12 official verticals"), it probably violates this pillar. Find the lower-level primitive instead.

---

## Pillar 2 — Scarcity is real

Matter, money, time, energy, information — all are conserved or finite. Nothing comes from nowhere.

**Implication:** Every dollar spent went to someone. Every resource extracted came from a plot. Every production output required real inputs. The economy is closed and accounting always balances.

**Test:** If you can describe a way to "get rich without anyone else getting poorer," scarcity is broken. Fix the primitive.

---

## Pillar 3 — Geography matters

Distance, terrain, climate, and adjacency aren't decoration — they create real friction and real opportunity.

**Implication:** Goods take time to move. Plots far from markets are cheaper. Coastal access is valuable. Choke points exist. Logistics is its own vertical.

**Test:** If a player's strategy doesn't change based on where their plot is, geography isn't doing its job.

---

## Pillar 4 — Information asymmetry creates markets

Not everything is public. Knowing things has cost. Speculation requires research.

**Implication:** Players don't see all prices everywhere. They don't know what's in unprospected plots. They don't see private contracts. They have to *learn* the market — and analytics businesses can sell that knowledge.

**Test:** If a player can know everything by opening a single dashboard, you've collapsed the market into a solved game. Hide something.

---

## Pillar 5 — Reputation persists

Players and businesses have identity. Their behavior over time is visible. Trust is earned and burnable.

**Implication:** Anonymous behavior is harder. Defaulting on a contract follows you. Reliable suppliers can charge a premium. Scammers eventually get priced out — or build new identities at high cost.

**Test:** If a player can do something terrible and have no consequences beyond the immediate transaction, reputation isn't doing its job.

---

## Pillar 6 — Solo and multiplayer share one engine

Every system must work in solo mode (against AI agents) and multiplayer (against humans) without forking the codebase.

**Implication:** AI agents are first-class — they participate via the same APIs as players. There's no "AI mode" that's a separate game. The simulation is authoritative; players and AI both query and act through the same primitives.

**Test:** If a feature only makes sense in one mode, you're probably building two products in a trench coat. Generalize it or scope it down.

---

## Pillar 7 — Mobile is a companion, not a port

The mobile app exists to monitor and quick-react. It does not exist to play the full game.

**Implication:** Don't try to fit "build a factory" onto a phone screen. Do fit "your supplier is offering a 12-month contract — accept, reject, counter?" Fit "your stock just dropped 8%, here's why." Fit "approve this $50K loan request."

**Test:** If a feature can't be done well in 5 seconds at a stoplight, it doesn't belong on mobile.

---

## How to use these pillars

1. **In design reviews:** Walk through the seven and ask which one this feature serves. If none, reconsider.
2. **In feature requests from players:** Players will ask for things that violate pillars (auto-resolve combat, instant travel, hidden info revealed, etc.). Politely refuse. Explain.
3. **In scope cuts:** If you have to cut something, cut the thing that least serves the pillars.
4. **In hiring/onboarding:** Anyone joining the project reads this doc first.

## Pillars that are *not* on this list (deliberately)

These came up in conversation and were considered but rejected as pillars. Some are values; some are tactical decisions; none rise to the level of immovable.

- **"Always be free-to-play"** — monetization is a tactical choice, not a pillar.
- **"Always 2D"** — currently true but a tactic, not a pillar. (If 3D ever made the experience meaningfully better, we'd consider it.)
- **"No PvP combat"** — a v1 scoping decision. Could change in distant future.
- **"Realistic graphics"** — irrelevant. The aesthetic is a downstream choice.

When stating "this is a pillar" to anyone, refer only to pillars 1–7.

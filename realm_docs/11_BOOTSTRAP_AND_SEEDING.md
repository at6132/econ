# 11 — Bootstrap and Seeding

> The single biggest risk of a 100% emergent economy: at launch, nothing works because everyone is waiting for someone else to do something. This doc is the strategy for avoiding that.

---

## The bootstrap problem, formally

In a real economy, the steel industry exists because there's already iron mining, coal mining, manufacturing, and demand for steel products. None of it appeared simultaneously. It evolved over centuries.

In Realm at launch, day 1, **nothing exists.** No iron supplier means no steel maker. No steel maker means no construction. No construction means no demand for steel. The economy would never start.

This kills emergent-economy games regularly. We have two main strategies and a few smaller ones.

---

## Strategy 1 — Solo mode is the bootstrap

Solo mode does not have this problem. AI agents play all the roles. The economy is "seeded" by hand-authored AI behavior in each scenario.

**Implication:** by shipping solo first, we don't even need to solve the bootstrap problem in v1. We solve it in v2+ when we add multiplayer.

This is the cleanest answer. **You should not panic about the bootstrap problem in v1.** It does not apply.

---

## Strategy 2 — Closed cohort launch (multiplayer v1)

When we open multiplayer, we don't open it to the public. We open it as a **closed cohort competition** — invite-only, 50 players hand-picked.

**Why this works:**
- We can pre-coordinate roles. Some players are encouraged to start in extraction. Others in shipping. Others in finance.
- 50 players in one shard is enough to have all major verticals represented from day 1.
- Hand-picked players are more committed and more likely to engage seriously.
- Time-boxed (e.g., 90-day season) means the bootstrap pain is bounded.

**This is also great marketing.** Closed cohorts generate stories, streams, and articles. Top performers earn invites to subsequent cohorts. By the time we open public multiplayer, multiple cohorts have run, mechanics are tuned, and there's a base of experienced players to seed the public servers.

---

## Strategy 3 — NPC seed economy (always present)

Even in multiplayer, there are some baseline AI agents:

- **NPC consumers.** Generic households that buy basic goods (food, fuel, clothing). They generate baseline demand. They are intentionally weak at price discovery — they pay the market rate, slightly inelastic. This means players who supply basic goods always have a baseline of customers.
- **NPC laborers.** Generic workers in populated regions. They will accept jobs at market wages. They quit if mistreated.
- **NPC banks (early game only).** A simulated bank that offers small loans to new players. Crappy terms, but available. Phases out as player-run banks emerge.
- **A small handful of NPC suppliers** for the most universal goods (energy, perhaps a base material or two). Same intent as banks: emergency provider, crappy prices, phases out.

**Critical:** NPCs are *worse than players.* They exist as a floor, not a competitor. Once player businesses serve a market well, NPC participation in that market is reduced.

NPC injections of money:
- NPC consumers spend money buying from players. That money has to come from somewhere.
- The simulation periodically tops up NPC accounts (this is the only "money creation" in the system, and it's bounded and visible).
- This is effectively a controlled inflation rate. You can adjust it to balance the economy.

---

## Strategy 4 — Frontier expansion zones

When the world has been carved up by established players and new players have nowhere good to go, the engine periodically opens **new regions** for plot claiming.

This solves the late-joiner problem: even if the original continent is fully claimed, there's always a frontier. New players can stake a claim on equal terms.

**Implementation:** the world map has "fog of war" zones initially. Periodically (every season, every quarter, on triggers) a new zone opens. New players can start there.

---

## Strategy 5 — Server seasons / resets

Some shards reset on a schedule. Every 90 days, the world is wiped and starts over. Players get fresh rankings, the bootstrap re-runs, etc.

**Pros:** persistent late-joiner problem solved. Fresh competitive integrity. Stream-friendly.

**Cons:** loses long-term continuity. Players who like building empires for years prefer permanent shards.

**Solution:** offer both. Some shards are seasonal (90-day). Some are permanent. Players choose.

---

## Strategy 6 — Starter packs / genesis bonuses

When a new shard opens, the first N players get *role-encouragement bonuses.* Not random class assignment — choose-your-role:

> "This shard needs: shipping (3 slots), finance (2 slots), agriculture (4 slots). Pick a role, get a 25% starting capital bonus."

This is soft-coordination. Players can ignore the bonus and do whatever, but the bonus pulls them toward filling roles.

**As the shard matures, bonuses phase out** — once shipping has enough providers, the shipping bonus disappears. The market rebalances itself once it's healthy.

---

## Strategy 7 — Tutorial scenarios that teach the bootstrap

In solo mode, one of the canonical scenarios should explicitly walk a player through *being part of a young economy.* The "Frontier" scenario from doc 08 is exactly this. By the time a player has lived through that scenario, they understand:
- "If no one's making iron, I should make iron."
- "If everyone's making iron, I should ship iron, not make it."
- "The first mover in a vertical has advantages."

This is *educational scaffolding* for when they enter a multiplayer shard. They know how to find an unfilled niche.

---

## Layered defense

The strategies above are layered, not alternatives. A shard at launch uses *all of them*:

1. **Pre-launch:** closed cohort launch, hand-picked players, role-suggestions
2. **Launch event:** NPC seed economy is fully populated, frontier zones revealed
3. **Day 1:** genesis bonuses encourage role-filling
4. **Day 30:** shard is mature; NPC participation drops as players take over
5. **Day 90:** if seasonal, reset and start over; if permanent, a frontier expansion opens

---

## Empty-economy detection

Even with all strategies, sometimes a market just doesn't form. We need to detect and respond.

**Health metrics per shard:**
- Number of distinct producers per material category
- Average market depth per asset
- New-player retention at day 7
- Average net worth growth in week 1

**Triggers and responses:**
- If energy supply drops below threshold → spawn temporary NPC energy provider with ugly prices (creates demand for player-run alternatives)
- If a region has no shipping → reduce land prices in that region (incentive for shipping-curious players to claim there)
- If a vertical has only 1 player → flag as monopoly risk; consider reduced barriers for new entrants

These are levers, not solutions. **Try not to use them.** The economy should self-regulate; these are emergency valves.

---

## What we're not doing

- We are not pre-defining "the wheat market exists from day 1."
- We are not seeding the economy with NPCs in every role at competitive prices.
- We are not making it so a new player can do well by following a script.

**The bootstrap exists** — it's part of the experience. Closed cohorts and named scenarios let us shape it without scripting it.

---

## Public mode launch sequence (target plan)

1. **Solo mode launches publicly.** A bunch of players play solo for months. We watch their behavior, gather data on what scenarios are sticky.
2. **Closed cohort 1.** ~50 players, invited from solo top performers. 90-day season. We learn.
3. **Closed cohort 2 + 3.** Increased size, refined mechanics. Marketing builds.
4. **Open beta.** 1 shard, public. Maybe with frontier expansion enabled aggressively.
5. **Public live.** Multi-shard, ongoing operation.

This sequence gives us many opportunities to learn before exposing the bootstrap problem at full scale.

---

## The big takeaway

**Don't try to solve the bootstrap problem all at once.** Solve it in solo (with AI agents). Then in closed cohorts (with curated players). Then in time-boxed seasons (with player coordination). Each step de-risks the next. By the time we open a permanent public shard, we've stress-tested the bootstrap mechanism multiple times.

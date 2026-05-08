# 13 — Phased TODO

> **This is the operational doc.** It is the build plan, with explicit phases, what gets built in each, and the test gate that must be passed before moving on.
>
> **Do not skip phase test gates.** They exist because skipping them is how projects like this die. Every phase produces a shippable, testable artifact.

---

## How to use this doc

1. You are at any moment in exactly one phase.
2. Each phase has an objective, a build list, and a test gate.
3. You do not move to the next phase until the test gate is passed.
4. If a test gate fails, you iterate within the current phase or revise the design.
5. If a test gate is consistently failing despite iteration, the design is broken — go back to the spec docs (01–11) and revise.

---

## Phase 0 — Spec & Foundation
**Duration estimate:** 2–4 weeks
**Goal:** Have a complete, internally-consistent design spec before writing engine code.

### Build list

- [ ] Read all of docs 01–12 end-to-end. Note disagreements with yourself.
- [ ] Update any docs where the design has shifted from this initial spec.
- [ ] Write 5 worked examples of player-invented businesses using only the 9 primitives. If any business *cannot* be expressed, the primitive set is incomplete — revise doc 03.
- [ ] Pick the v1 simulation language (Python recommended) and stack (per doc 09).
- [ ] Set up the project repository with a clean directory structure.
- [ ] Write a 1-pager pitch (extract from doc 01) that you can hand to anyone in 2 minutes.
- [ ] Write the glossary (doc 15) — precise definitions of every term used in design discussions.

### Test gate

> **Can you describe, in one paragraph each, exactly what 5 different player-invented businesses look like — including which primitives they use, what their daily activities are, and how they make money?**
>
> If yes → Phase 1.
> If no → the primitives spec is incomplete. Revise doc 03 and try again.

### How to test before moving on

1. Pick 5 business types: e.g., shipping company, SaaS provider, bank, surveyor, speculator.
2. For each one, write a 1-paragraph description without inventing any new mechanics.
3. Have someone else (Shmuel, a friend) read your descriptions and ask: "could you actually run this business in this game?" If they can imagine it, you're done.
4. If they push back ("how would they actually X?"), that's a missing primitive — go fix doc 03.

---

## Phase 1 — Solo Engine Prototype (Ugly But Functional)
**Duration estimate:** 8–12 weeks
**Goal:** A playable solo prototype that proves the core economic loop is fun. Ugly UI is fine. No graphics required.

### Build list

**Engine core:**
- [ ] Tick-based simulation loop with deterministic time
- [ ] World generation (small: 30–50 plots in a single region)
- [ ] Plot system (Primitive 1) — terrain, hidden subsurface, ownership
- [ ] Material system (Primitive 2) — ~10 starter materials with realistic properties
- [ ] Capital system (Primitive 5) — accounts, atomic transfers, conservation enforced at data layer
- [ ] Production system (Primitive 6) — ~5 hand-authored recipe templates (e.g., timber → lumber, ore → metal)
- [ ] Movement system (Primitive 4) — basic transport with time and cost
- [ ] Order books (Primitive 7b) — for materials with sufficient volume
- [ ] P2P trade (Primitive 7a)
- [ ] Basic contracts (Primitive 8) — supply contracts, employment contracts only
- [ ] Reputation tracking (Primitive 9 placeholder — just count contracts honored vs breached)

**AI agents:**
- [ ] ~6 Tier 1 (behavioral) agent archetypes — consumer, generic supplier, generic laborer, etc.
- [ ] No Tier 2 yet
- [ ] No Tier 3 yet

**Frontend:**
- [ ] Basic Next.js app
- [ ] World map view (just a colored grid, no Pixi.js yet)
- [ ] Plot detail view (tables + buttons, no schematic)
- [ ] Market view (table-based order book + minimal chart)
- [ ] Inventory view (table)
- [ ] Build menu (list of buildings with costs)
- [ ] Hire menu (list of workers with wages)
- [ ] Action log (text feed of events)

**Persistence:**
- [ ] SQLite save files
- [ ] Save/load a world

**Skipped in this phase:**
- ❌ Graphics polish
- ❌ Mobile app
- ❌ User-code layer
- ❌ Tier 3 LLM agents
- ❌ Multiplayer
- ❌ Multiple scenarios — just the "Frontier" scenario from doc 08

### Test gate

> **Get 3–5 strangers to play the prototype for 1 hour. After their session, ask them: "would you keep playing if I gave you another hour?" 3 of 5 must say yes.**

### How to test before moving on

1. Don't play it yourself for the test (you're biased).
2. Recruit 3–5 people who are NOT building the game. Ideally a mix: someone who plays sim games, someone who doesn't, someone technical, someone non-technical.
3. Sit them down with the build, give them a 2-minute orientation, and let them play for 1 hour. Don't help unless they're truly stuck.
4. Watch them. Note specifically:
   - When are they confused?
   - When do they smile, lean in, swear, or get excited?
   - When do they zone out?
   - At what point do they start making real decisions vs guessing?
   - Do they want to keep playing at the end?
5. Survey afterwards: "would you keep playing for another hour?"
6. **If 3 of 5 say yes — pass.** If fewer, iterate. The fix is almost always in the design (the primitives, the first-hour script), not the UI.

### Common failure modes in this phase

- **"It's confusing."** First hour script (doc 08) needs work. Add scaffolding without scripting.
- **"There's nothing to do."** AI agents are too passive; market activity is too low. Increase agent activity.
- **"The numbers feel arbitrary."** Players can't connect cause and effect. Add more visible information about why prices move.
- **"It's a spreadsheet, not a game."** That's actually fine for this phase; we're testing whether the *economics* are fun. Visual polish comes in Phase 2.

---

## Phase 2 — Solo Polish & Visual Identity
**Duration estimate:** 8–12 weeks
**Goal:** Take the proven prototype and make it visually compelling. Add Tier 2 AI agents. Add named scenarios.

### Build list

**Visuals:**
- [ ] Pixi.js world map view (colored terrain, plot boundaries, ownership shading)
- [ ] Schematic plot view (drag-drop production flow)
- [ ] Real charting (Recharts) for market view
- [ ] Polished UI components (panels, command palette, keyboard shortcuts)
- [ ] Notification system (in-app toaster)
- [ ] Settings menu (game speed, pause, save management)

**Engine extensions:**
- [ ] Tier 2 (optimizing) AI agents — at least 4 archetypes (market-maker, logistics, production-planner, employer)
- [ ] More materials (~25 total, covering most starter strategies)
- [ ] More recipe templates (~15 total)
- [ ] Better contract templates (loan, equity, service-subscription stub)
- [ ] Surveying mechanic (reveal subsurface info at cost)
- [ ] Decay implementation per Law 5
- [ ] Information cost system per Law 6 (basic — historical price data costs money)

**Content:**
- [ ] 3 scenarios in addition to "Frontier": "The Cartel," "The Bootstrapper," "The Speculator" (doc 05)
- [ ] Scenario selection UI

**Skipped in this phase:**
- ❌ Mobile app
- ❌ User-code layer
- ❌ Tier 3 LLM agents
- ❌ Multiplayer

### Test gate

> **Get 5 strangers to play for 5+ hours each (across multiple sessions, ideally a week of self-directed play). At the end: at least 3 of 5 say "I'd buy this for $30 today."**

### How to test before moving on

1. Recruit 5 testers (different from Phase 1 testers if possible — fresh eyes).
2. Give them the build with no time limit. Tell them to play it like they would a game they bought.
3. Check in after 1 day, 3 days, 7 days. Ask:
   - "How much have you played?"
   - "What kept you coming back / what made you stop?"
   - "What was the most interesting moment?"
   - "What was the most frustrating moment?"
4. After 7 days, ask: **"If this game cost $30, would you buy it?"** 3 of 5 must say yes.
5. Bonus signals: testers organically post about the game online, share screenshots, tell friends. These are stronger than the survey answer.

### Common failure modes

- **Players stop after ~3 hours** — the late-game lacks depth. Expand the contract system, add more agent personalities.
- **Players say "I figured out the optimal strategy"** — the AI is exploitable. Tier 2 agents need more variety.
- **Players say "I want to play with friends"** — that's a great signal but it's Phase 5+. Note it.

---

## Phase 3 — Solo Launch
**Duration estimate:** 6–10 weeks (from start of phase to public launch)
**Goal:** Ship solo mode commercially. Build distribution, monetization, support. This is when Realm becomes a real product with real users.

### Build list

**Tier 3 LLM agents:**
- [ ] LLM agent runtime (Anthropic API integration)
- [ ] Memory system (rolling window + long-term summary)
- [ ] 5 named characters with distinct personalities (per doc 06)
- [ ] Cost monitoring + per-session budget caps

**Production readiness:**
- [ ] Stable build pipeline
- [ ] Crash reporting
- [ ] Telemetry (anonymous, opt-in)
- [ ] Save file forward-compatibility (saves from v1.0 work in v1.1+)
- [ ] Auto-update mechanism

**Distribution:**
- [ ] Steam page (or itch.io, or self-hosted, or all three — your call)
- [ ] Trailer / launch video
- [ ] Marketing copy and screenshots
- [ ] Demo version (limited scenario, no save)

**Monetization decision:**
- [ ] Decide pricing model (one-time purchase recommended, $25–$50)
- [ ] Set up payment processing
- [ ] Set up email collection / newsletter

**Support infrastructure:**
- [ ] Documentation site
- [ ] Discord (or equivalent) for community
- [ ] Bug report flow

### Test gate

> **Launch publicly. Within 30 days of launch: at least 200 paying users with >70% retention at day 7, and a Steam (or equivalent) rating averaging 80%+.**

### How to test before moving on

1. Soft-launch to a small group first (mailing list, beta testers, friends-of-friends).
2. Monitor crash rate, bug reports, telemetry. Fix critical issues.
3. Public launch.
4. Watch the first 30 days carefully:
   - How many people buy?
   - What's day-1, day-7, day-30 retention?
   - What are reviews saying?
   - What are players asking for?
5. **If retention is below targets**, the design has a flaw at scale. Address before moving to Phase 4.
6. **If reviews flag the same issue repeatedly**, prioritize that.

### What success in this phase enables

- Revenue to fund Phase 4+
- A community to draw closed-cohort participants from
- Press / streamer attention
- A library of player feedback to inform multiplayer design

---

## Phase 4 — User-Code Layer (Solo)
**Duration estimate:** 12–16 weeks
**Goal:** Add the user-code/services layer to solo mode. Players can write code, deploy services, subscribe to other services (which in solo mode are AI-generated or pre-shipped).

### Build list

**User-code runtime:**
- [ ] Lua sandbox (sandboxed interpreter with restricted stdlib)
- [ ] Read API (per doc 07)
- [ ] Write API (per doc 07)
- [ ] Service definition + publication
- [ ] Resource metering (CPU + storage budgets, billed in in-game currency)
- [ ] Service marketplace UI

**Block-based programming UI:**
- [ ] Visual block editor (drag-drop blocks)
- [ ] Compilation from blocks → Lua
- [ ] Beginner templates ("auto-restock," "price alerts")

**Solo-mode service ecosystem:**
- [ ] Pre-shipped services that AI agents publish (so the market isn't empty)
- [ ] Services that the player can subscribe to
- [ ] Services that the player can create and "sell" to AI agents

**In-game IDE:**
- [ ] Code editor (Monaco or CodeMirror)
- [ ] Live preview / test environment
- [ ] Debugging tools (logs, breakpoints if feasible)

### Test gate

> **At least 30% of returning players (week-2 cohort) deploy at least one service or use the block editor non-trivially. At least 50% of testers can describe a service they wish existed (showing they understand the platform's value).**

### How to test before moving on

1. Release Phase 4 as a free update to existing solo-mode owners.
2. Telemetry: track who opens the IDE, who writes code, who deploys, who subscribes to services.
3. Survey: "what would you build if you had time?" — read the answers.
4. Interview 5 active users about their experience with the user-code layer.
5. **If <30% engage with the layer**, the UX is too hard. Iterate (more templates, simpler block editor, better tutorials).
6. **If users describe interesting services they'd build**, you've validated demand for the platform.

---

## Phase 5 — Multiplayer Foundations + Closed Cohort 1
**Duration estimate:** 16–24 weeks
**Goal:** Ship the multiplayer infrastructure and run the first 50-player closed cohort.

### Build list

**Multiplayer infrastructure:**
- [ ] Authoritative server architecture
- [ ] Postgres-based state (migrate from SQLite for multi)
- [ ] Real-time WebSocket layer
- [ ] Auth (email + password, OAuth optional)
- [ ] Identity / account management
- [ ] Anti-cheat (mostly automatic via the determinism/audit-log architecture)

**Bootstrap mechanics:**
- [ ] Genesis bonuses for first-N players in different verticals
- [ ] NPC seed economy (consumers, laborers, baseline banks/utilities)
- [ ] Frontier zone reveal mechanic

**Cohort tooling:**
- [ ] Invite-only registration
- [ ] Season management (start, run, end, ranking, archive)
- [ ] Live leaderboard
- [ ] Spectator mode (so non-participants can watch)

**Operations:**
- [ ] Monitoring + alerting
- [ ] Backup + disaster recovery
- [ ] Customer support workflow
- [ ] Moderation tools

### Test gate

> **Closed Cohort 1 runs for its full season (90 days) with: <5% participant dropout, <2 hours of unplanned downtime total, no exploits affecting >5% of player state, and at least 60% of participants saying they'd join Cohort 2.**

### How to test before moving on

1. Recruit 50 cohort participants from solo-mode top performers.
2. Run a 7-day pre-season "stress test" with 20 of them. Find and fix major bugs.
3. Launch the 90-day season.
4. Monitor: server health, player engagement, exploits, bugs.
5. Run weekly retrospectives during the season. Fix critical issues live.
6. End-of-season survey: would they return? what worked? what didn't?
7. **If the cohort completes successfully**, multiplayer is ready for Phase 6.
8. **If it falls apart** (mass exit, major exploits, infra failure), do *not* open a public mode. Iterate and run Cohort 2 first.

---

## Phase 6 — Closed Cohorts 2-N + Public Open Beta
**Duration estimate:** 9–18 months
**Goal:** Run multiple cohorts, refine the multiplayer mechanics, then launch a public open beta.

### Build list

- [ ] Cohort 2 (with lessons from Cohort 1)
- [ ] Cohort 3 (larger, ~150 players)
- [ ] Public open beta (1 shard, free or low-cost entry)
- [ ] Tournament / event tooling
- [ ] Streamer / content-creator tools (replay export, embed widgets)
- [ ] Mobile companion app v1 (read-only + key flows from doc 10)

### Test gate

> **Public open beta runs for 90 days with: 1000+ daily active users at peak, 40%+ day-30 retention, no critical exploits, and a steady-state economy (no hyperinflation, healthy market depth across major asset classes).**

### How to test before moving on

1. Open beta with marketing push.
2. Daily monitoring of all KPIs.
3. Address economic dysfunction immediately if observed.
4. Iterate on player feedback.
5. **If the open beta succeeds**, proceed to Phase 7.
6. **If it shows systemic problems**, fix and re-run before opening permanent multiplayer.

---

## Phase 7 — Public Persistent Multiplayer
**Duration estimate:** ongoing
**Goal:** Open permanent multiplayer shards. Realm becomes a live ongoing product.

### Build list

- [ ] Multi-shard architecture
- [ ] Shard selection UI
- [ ] Cross-shard player profile (single account, multiple worlds)
- [ ] Subscription / monetization for multiplayer
- [ ] Mobile companion v2 (full functionality per doc 10)
- [ ] Player-issued currencies (Primitive 5 v2)
- [ ] Advanced financial primitives (derivatives, insurance, bond markets)
- [ ] Player governance / corporations (multi-player businesses with shareholders)

### Test gate

> **There is no "exit gate" for this phase. The phase is live operation of a successful game.** Track ongoing health: DAU, MAU, retention, ARPU, NPS. Maintain.

---

## Phase 8+ — Long-term roadmap

Beyond Phase 7, possible directions:

- **Player governance / nations.** Players form regions, levy taxes, regulate.
- **More user-code language options.** Not just Lua. Maybe a higher-level visual language.
- **Realm Industries.** A meta-game where outstanding player creations get featured / spotlighted.
- **Realm API.** Third-party tools, websites, analytics services tap into the public game state.
- **VR / spatial visualization.** A 3D layer *on top of* 2D for atmosphere (not for gameplay).
- **Spinoffs** — single-player narrative games using the engine.

These are not commitments. They are possibilities to evaluate as the game evolves.

---

## Cross-cutting hygiene tasks (every phase)

These run throughout, not as discrete deliverables:

- [ ] Update the spec docs whenever a design decision changes
- [ ] Maintain the glossary
- [ ] Quarterly risk review (doc 12)
- [ ] Regular playtests (don't go more than 4 weeks without one)
- [ ] Performance monitoring
- [ ] Backup of save files / database

---

## A note on time estimates

The ranges above are honest but optimistic. As a solo or small-team developer, expect each phase to take 1.5x–2x the estimate. **That's fine.** The phasing is what matters — each phase produces a real artifact.

Total realistic timeline:
- Phase 0–1: 3–6 months
- Phase 2: 3–6 months
- Phase 3 (solo launch): 6–9 months from start
- Phase 4: 9–15 months from start
- Phase 5 (closed cohort 1): 18–24 months from start
- Phase 6 (open beta): 27–36 months from start
- Phase 7 (live multiplayer): 3+ years from start

If solo (Phase 3) launches in year 1.5, the project has succeeded. Everything beyond is upside.

---

## When you're stuck

If you hit a wall in any phase:

1. Re-read the relevant spec doc. Often the answer is already there.
2. Re-read the pillars (doc 02). Make sure you haven't drifted.
3. Look at the test gate. Are you working toward it, or have you wandered?
4. Talk it through with someone (Shmuel, a friend, even Claude).
5. If the wall is fundamental — the design itself isn't working — go back to Phase 0 and revise the spec. **Better to admit the problem early than to ship a broken design.**

---

## The most important sentence in this doc

**Do not skip phase test gates.** They are how this project ships instead of dies.

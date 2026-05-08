# 06 — AI Agent Design

> AI agents are first-class players in solo mode and provide seed economic activity in public mode. This is one of the most strategically important systems in the game — it's what makes solo mode a complete product and what plays directly to your existing strengths in agent design.

---

## The three tiers

We use three tiers of AI agents in production. Each fills a different role.

| Tier | Tech | Role | Volume |
|---|---|---|---|
| 1. Behavioral | Hand-coded rule-based | Generic background economy | Hundreds per world |
| 2. Optimizing | Algorithmic search / RL-lite | Mid-tier rivals, fill-in roles | Tens per world |
| 3. LLM-driven | Real LLM + structured tools | Named "characters," major rivals | Single digits per world |

The trick: **same API for all three tiers.** They all act on the world via the same simulation primitives a human player would. The difference is how they decide what to do.

---

## Tier 1 — Behavioral agents

**What they are:** Hand-coded rule-based NPCs running deterministic strategies.

**Why they exist:**
- Fill out the world cheaply (hundreds per simulation, $0 marginal cost)
- Provide a baseline economy (buyers, sellers, workers)
- Predictable enough that designers can balance the rest of the game around them

**Architecture:**
Each behavioral agent has:
- A "role" (consumer, generic supplier, generic laborer, generic shopkeeper)
- A simple goal function (e.g., "buy enough food to survive each day, save the rest")
- A small finite state machine that picks actions based on observed world state
- No memory beyond the current state (purely reactive)

**What they can do:**
- Place buy/sell orders within their role
- Accept employment from players
- Fulfill simple contracts
- Migrate (workers move toward higher wages)
- Go bankrupt / quit (they exit the simulation if their goal becomes infeasible)

**What they cannot do:**
- Initiate complex contracts
- Run businesses themselves
- Use code / programmable services
- Form alliances or conspiracies

**Implementation:** Pure code, runs locally in solo mode (even client-side), runs on cheap workers in public mode. Approx 100 lines per role. Probably ~10 distinct roles cover 90% of needs.

---

## Tier 2 — Optimizing agents

**What they are:** Algorithmic agents that solve well-defined optimization problems against the live game state.

**Why they exist:**
- Provide credible mid-tier competition for the player
- Run businesses that require optimization (logistics, market-making, production planning)
- Offer the "I'm being out-played by something smarter than me" feeling without LLM cost

**Architecture:**
Each Tier 2 agent has:
- A specific problem class (e.g., "I am a market-maker for commodity X" or "I am a shipping company optimizing route schedules")
- A solver appropriate to that problem (linear programming, search, simple online learning)
- Memory of past performance (price history, contract success rates)
- A budget (CPU and capital constraints)

**What they can do:**
- Run actual businesses with measurable performance
- React to changes in the market
- Adjust strategy if their KPIs trend bad
- Form simple multi-step plans
- Honor and propose contracts

**What they cannot do:**
- Negotiate in natural language
- Form personality-driven relationships
- Surprise the player with creative strategies they weren't pre-programmed for

**Implementation:** Mid-effort. Probably ~5–10 archetypes covering common business types. Each archetype is ~500 lines + a solver library. Reusable across scenarios.

---

## Tier 3 — LLM-driven named agents

**What they are:** Full LLM-backed agents with personality, memory, and natural-language negotiation.

**Why they exist:**
- They are the *characters* of solo mode. The named rivals who taunt you, betray you, scheme, build empires, do unexpected things.
- They generate stories. They make solo mode emotionally engaging in a way no rule-based system can.
- They are the differentiator vs every other economy sim ever made.

**Constraint:** Expensive. At $X/turn LLM cost, you cannot run 1000 of these. You can run 5 to 15 per world.

**Architecture:**
Each Tier 3 agent has:
- A persistent personality (a system prompt: who they are, what they want, how they talk, what their style is)
- A long-term memory (stored summaries of past events, key relationships, grudges, strategies)
- A short-term context (recent events, current goals)
- A toolset matching the simulation's player API (place order, propose contract, send message, hire labor, build, etc.)
- A "thinking budget" — how often they re-plan (maybe once per game-day, not every tick)
- A speech style — they can send messages to the player and other agents in natural language

**Decision loop (per game-day or on event triggers):**
1. Pull current world state relevant to this agent
2. Pull recent events involving this agent
3. Pull memory summary
4. LLM call: "given context, what do you want to do?"
5. Validate the plan against simulation rules
6. Execute via tool calls
7. Update memory

**Anti-pattern to avoid:** Don't make Tier 3 agents into chatbots that just *talk*. They must *act*. Their messages should reflect their actions, not replace them. A Tier 3 agent that says "I'm going to corner the iron market" should then actually try to corner the iron market over the next few game-days, with all the buying, contracting, and political maneuvering that implies.

**Personality examples for v1 (illustrative — final cast TBD):**
- *"Margaux the Industrialist"* — methodical, vertical-integration obsessed, builds slowly but unstoppably. Tone: quiet, polite, ruthless. Plays a long game.
- *"Rico the Speculator"* — pure trader, no plots beyond legal minimum, lives in the order books, brash. Tone: loud, swears, bluffs.
- *"The Consortium"* — actually three coordinated agents that pretend to be independent but secretly collude. Reveal-of-conspiracy is a story arc.
- *"Quiet Anna"* — runs a SaaS empire, never visible, but her code is in everyone's stack. Players notice her only when her services go down.
- *"Kingfisher"* — banker, gives loans on hard terms, builds informational power.

**Implementation cost:** Real money. A Tier 3 agent making 1 LLM call per game-day at 1 game-day = 1 real-hour, with a $0.05 call, costs $0.05/hour = $1.20/day = ~$36/month. With 10 of them in a paused-or-not-paused solo game, that's $360/month per world if always-running. **In solo mode this is bounded by the player's session length** — the agents only "tick" when the world is unpaused. A typical player playing 5 hours/week = $1.50/week of LLM spend per Tier 3 agent. Manageable.

**For public mode:** Tier 3 is cost-prohibitive at scale. Most public-mode background agents are Tier 1/2; Tier 3 is reserved for special "named NPCs" that act as world figures (a few dozen per shard) and their actions are persistent across all players.

---

## The unified agent API

All three tiers act on the world via the same API a human player uses. This is critical.

**The API exposes (read):**
- Public world state (geography, prices, public reputation)
- Agent's own private state (inventory, accounts, contracts)
- Recent observations (events affecting this agent)

**The API exposes (write):**
- Place orders (buy/sell)
- Propose contracts
- Accept/reject incoming proposals
- Hire / fire labor
- Build / improve plots
- Move goods
- Send messages to other agents/players
- Deploy / call code services

The engine validates every action. If a Tier 3 agent's plan violates physics (tries to spend money it doesn't have, build on a plot it doesn't own), the action fails — same as it would for a human player.

**This means:** human players, Tier 1, Tier 2, and Tier 3 agents are *symmetric*. The simulation cannot tell them apart. This is what makes solo and multiplayer share an engine.

---

## The hardest design problem here

**How do AI agents stay challenging without being unbeatable?**

If Tier 3 agents are too smart, they become frustrating. If they're too dumb, they're boring.

**Approach for v1:**
- Each agent has a *handicap profile* — they intentionally play sub-optimally in known ways. Maybe Rico ignores some opportunities because he's "lazy." Maybe Margaux is slow to react.
- Difficulty is tunable per scenario.
- Agents have biases that the player can learn and exploit. Their predictability is a design feature, not a bug.
- We don't try to make them "win"; we try to make them *interesting*.

**Approach for v2+:**
- Self-play training (agents play against each other, learn).
- Player-data-informed (most-successful human strategies become AI strategies, with credit).

---

## Memory and continuity

Tier 3 agents need persistent memory or they feel amnesiac. The memory layer is its own design problem.

**v1 memory architecture:**
- A rolling window of recent events (last N days)
- A long-term summary (LLM-generated periodically, compresses old events)
- A relationship graph (who do I trust, who has wronged me, who do I owe)
- Major events stored verbatim (the time the player betrayed me, etc.)

**Failure modes to avoid:**
- Memory bloat (the prompt grows until the LLM call is too expensive)
- Memory drift (the agent forgets things that should matter)
- Memory hallucination (the agent "remembers" things that didn't happen)

**Mitigation:** Periodic memory compression with explicit "preserve verbatim" tags on major events.

---

## How AI agents fit into solo mode flow

A typical solo-mode session:

1. Player loads scenario. World is generated. AI agents are instantiated with their personalities and starting positions.
2. Time flows. Behavioral and Optimizing agents tick continuously. Tier 3 agents tick on a slower cadence.
3. Player takes actions. AI agents observe and may react in their next tick.
4. Tier 3 agents may send messages to the player ("I notice you're buying a lot of copper. We should talk."). Player can respond or ignore.
5. Over time, named agents pursue their long-term goals. Some succeed, some fail.
6. Player can pause to think.
7. Player can save and resume later.

The fantasy is *you're playing against a small cast of distinct characters, each with their own arc.* That's solo mode's emotional core.

---

## Public mode considerations

Public mode is dominated by humans, but we still need NPCs for the bootstrap problem and ongoing baseline.

- **NPC consumers** (Tier 1) — buy goods at market, generate baseline demand
- **NPC laborers** (Tier 1) — fill labor pools in populated regions
- **A few named figures** (Tier 3) — fixtures of the world, persistent across all players, make the world feel alive

NPCs in public mode should be *less competent* than humans on average. Their role is to provide structure, not to challenge.

---

## Build order

In line with doc 13:

- **Phase 1 (solo prototype):** Tier 1 agents only. Behavioral, dumb, cheap. Just enough to populate the world. Probably 5–10 archetypes.
- **Phase 2 (solo polish):** Add Tier 2 agents. Real businesses run by algorithms.
- **Phase 3 (solo polish, named characters):** Add Tier 3 agents. ~5 named characters per scenario.
- **Phase 5+ (multiplayer):** Re-use the same agent infrastructure. Public mode uses mostly Tier 1/2 with a few persistent Tier 3 named figures.

The agents are not a v1 ship blocker, but they are a v2 ship blocker. The *fun* of solo mode requires Tier 3.

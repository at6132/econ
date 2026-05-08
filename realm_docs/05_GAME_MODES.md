# 05 — Game Modes

Three modes. One engine. Each is a real product.

---

## Mode 1 — Solo Mode

**The setup:** You are alone in a world full of AI agents that act as your competitors, customers, suppliers, and rivals.

**Who it's for:**
- New players learning the game
- Players who want experimentation without consequence
- Players who don't have time for a persistent multiplayer commitment
- Players who want narrative/scenario play

**Core characteristics:**
- Pausable
- Configurable speed (1x, 2x, 4x, max)
- Save/load anywhere
- Replayable from saved seed
- Worlds are smaller (10s of plots, ~5–15 named AI agents + dozens of generic agents)
- Often scenario-based (see Scenarios below)

**Why this is a real product, not a tutorial:**
Solo mode is shipped as a complete game. You can buy it, play it for hundreds of hours, and never go online. It validates the entire design before any multiplayer infrastructure exists. **It is also the existence test of the project — if solo isn't fun, nothing built on top will be.**

### Solo-mode scenarios

A scenario is a curated starting world: pre-defined map, pre-defined AI agents with known personalities and strategies, pre-defined initial conditions, and an optional objective.

**Example scenarios for v1:**

- **"Frontier."** Empty continent, you and 8 AI agents start with similar resources. Goal: reach $1M net worth. Open-ended sandbox.
- **"The Dying Capital."** A region whose economy has been mismanaged. Inflation, broken supply chains, unhappy populace. Goal: stabilize and rebuild.
- **"The Cartel."** Three AI agents have cornered the energy market. Goal: break the cartel without going bankrupt.
- **"The New Industrial Revolution."** A new material is discovered that disrupts existing supply chains. Goal: position yourself before the markets price it in.
- **"The Speculator."** You start with cash but no plot. Goal: build wealth purely through trading and SaaS — no physical extraction.
- **"The Bootstrapper."** No starting capital. Goal: get to $100K from labor alone.

**Scenarios are content** — adding more of them is one of the cheapest ways to extend the game's lifespan after launch.

**Important: scenarios use the same engine as everything else.** They're not scripted experiences. They're configured starting conditions. Once a scenario starts, the AI agents play it for real, and the player's interaction is genuine, not on-rails.

---

## Mode 2 — Public Persistent World

**The setup:** A real, persistent, shared multiplayer world. Many players, NPC seed agents, real economy.

**Who it's for:**
- Players who've graduated from solo and want real stakes
- Players who want to be part of a larger story
- The hardcore and the long-haul

**Core characteristics:**
- Never pauses
- Slow real-time (1 game-day = 1 real-hour)
- Reputation is permanent and follows you
- Plots are scarce; the land rush is a real event at server launch
- Markets are global within the shard
- Closed accounts and verified identity
- Mobile companion app heavily used here

**Server architecture:**
- Multiple shards possible (each is its own world)
- Each shard has a launch event, a "land rush" period, and a steady state
- Shards may be permanent (multi-year) or seasonal (see Mode 3)

**NPC role in public mode:**
NPCs exist in public mode to:
- Provide a baseline of demand (NPC consumers buy goods)
- Provide a baseline of labor (NPC workers can be hired)
- Provide rare seed services (NPC banks for early-game small loans)

But NPCs are intentionally *worse than players* at most things. The fun comes from out-competing other humans, not from grinding against weak NPCs.

---

## Mode 3 — Competitive Seasons / Closed Cohorts

**The setup:** A time-boxed multiplayer world with curated participants and explicit competitive structure.

**Variants:**

### Season server (open competition)
- Time-boxed (e.g., 90 days)
- Anyone can enter (possibly with eligibility based on solo-mode performance or prior season standings)
- Resets at end of season
- Final rankings published
- Possibly: cosmetic rewards, leaderboard glory, eligibility for invite-only events
- Top performers get an invite to the next closed cohort

### Closed cohort (invite-only)
- Hand-picked participants (e.g., 50 players)
- Often themed (the "OG cohort," the "media cohort," the "academic cohort")
- May have prizes
- Stream-friendly format — events, narrative arcs, broadcasts
- Functions as marketing, balance-testing, and high-prestige play

**Why these matter:**
- They create a competitive top-of-funnel that flows into the public mode
- They generate content (streamers, articles, dramatic stories)
- They let us test new mechanics without risking the public economy
- They're a cleaner way for us to monetize at the top end (invitation tiers, season pass, etc.)

---

## Mode 4 — Custom servers (post-launch, lower priority)

Players can run their own server with custom rules. Not a launch feature. Mentioned for completeness because the engine should be designed *not to preclude this.*

**Implication:** The engine should be deployable as a self-contained service. Even if we don't expose this in v1, we should architect for it.

---

## Mode comparison table

| Aspect | Solo | Public Persistent | Competitive Season |
|---|---|---|---|
| Players | 1 + AI | Many humans | Many humans |
| Pause? | Yes | No | No |
| Time scale | 1x to max | 1 day = 1 hour | 1 day = 1 hour |
| Save / load | Yes | No (server-side persistent) | No (season ends → reset) |
| Reputation persistence | Within scenario | Permanent | Within season |
| Scarcity of plots | High but resettable | High and permanent | High, season-bounded |
| Win condition | Optional per scenario | None | Yes (rankings) |
| Best for | Learning, experimentation, story | Lifestyle play | High-stakes competition |

---

## Cross-mode interactions

A player has one Realm account. That account has:

- A profile, name, identity (one identity across all modes — no aliases in v1)
- A solo-mode save file collection
- A public-mode standing within each shard they participate in
- A competitive-season history with rankings

**Reputation does not transfer from solo to public** (you'd farm it). But your *solo-mode achievements* are visible on your profile, and may unlock cohort eligibility.

**Currency does not transfer between modes.** Each mode is its own economy. (No real-world currency conversion either — Realm dollars are not crypto.)

---

## Building order for the modes

This is critical and is reflected in doc 13:

1. **Solo mode first.** It's the existence test. Ship it. Sell it.
2. **Mobile companion** can come during/after solo, since solo plays well with companion app for "did my AI rivals do anything since I last played?"
3. **Competitive seasons before fully open public mode.** Time-boxed multiplayer is much easier to operate than persistent. Use seasons to validate multiplayer mechanics.
4. **Public persistent mode last.** This is the operationally hardest mode. Long-running servers, anti-cheat, support, moderation, the works. Don't open until competitive seasons have proven the mechanics.

This sequencing means the project ships something real every 6–12 months, not a single big launch in year 5.

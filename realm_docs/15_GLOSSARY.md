# 15 — Glossary

> Precise definitions of every term used in the Realm spec. When two docs (or two people) seem to disagree, check here first — usually one of them is using a term loosely. Update this doc when terminology shifts.

---

## A

**Account.** A financial entity that holds capital. Owned by a player, business, or the system. Identified by an account ID. Balances are mutated only via transactions.

**Action.** Any state-changing operation a player, AI agent, or service attempts: place order, propose contract, hire labor, build, transfer money, etc. Actions are *proposed*; the engine validates and either commits or rejects.

**Agent.** An AI participant in the simulation. See **Tier 1 / Tier 2 / Tier 3 agent**.

**Asset.** Anything that can be held, valued, or traded: materials, equity in a business, currency, a contract receivable. Assets always have an owner and a location.

**Authoritative simulation.** The principle (Law 10) that the simulation is the only source of truth about world state. Clients propose; the engine decides.

---

## B

**Behavioral agent.** See **Tier 1 agent**.

**Block-based programming.** The visual drag-and-drop interface for the user-code layer (Phase 4+), aimed at non-programmers. Compiles to Lua under the hood.

**Bootstrap problem.** The risk that an emergent economy can't start because every business waits for another business to exist first. See `11_BOOTSTRAP_AND_SEEDING.md`.

**Business.** A player- or agent-run economic enterprise. Not a primitive — businesses *emerge* from compositions of primitives (plots + capital + labor + contracts + sometimes code).

---

## C

**Capital.** Primitive 5. Money. Conserved. Held in accounts.

**Closed cohort.** An invite-only multiplayer scenario, hand-picked participants, time-boxed. Used for high-prestige play, balance testing, and marketing. See `05_GAME_MODES.md`.

**Code service.** See **Service**.

**Cohort.** A group of players in a time-boxed multiplayer scenario. See **Season**.

**Conservation.** Law 1. Matter and money cannot be created or destroyed except through designed channels.

**Contract.** Primitive 8. A multi-step, multi-condition, engine-enforced agreement between parties. Contracts are *templates plus parameters,* not free-form code. Templates: supply, loan, employment, equity, service-subscription.

**Contract template.** A predefined contract structure with named parameters (price, quantity, duration, etc.). Players parameterize templates rather than writing contracts from scratch.

---

## D

**Decay.** Law 5. Buildings, equipment, vehicles, and stockpiles deteriorate without maintenance. Code services do not decay but require periodic CPU payment.

**Determinism.** Law 9. Same starting state + same inputs = same outputs. Enables replays, debugging, save/load, anti-cheat.

**Direct P2P trade.** Primitive 7a. A one-shot mutual exchange between two specific parties. Distinct from order-book trading.

---

## E

**Energy.** A required input to production (Law 4). A tradeable good. Local grids — energy doesn't transmit globally for free.

**Engine.** The simulation core. Authoritative. Tick-based. Deterministic.

**Existence test.** The principle that solo mode must prove the design is fun *before* multiplayer infrastructure is built. If solo isn't fun, nothing built on top is fun.

---

## F

**Frontier zone.** A region of the map periodically opened for new plot claims, used to mitigate the late-joiner problem in long-running shards. See `11_BOOTSTRAP_AND_SEEDING.md`.

---

## G

**Game-day.** A unit of in-game time. In public mode: 1 game-day = 1 real-hour. In solo mode: configurable.

**Genesis bonus.** A starting-capital boost given to early players in a new shard who fill needed roles (shipping, finance, agriculture, etc.). Phases out as the role becomes saturated.

---

## I

**Identity.** A player's persistent in-game self. Has a reputation, a contract history, a public profile. New identities have a cost (Law 8) to prevent reputation laundering.

**Information cost.** Law 6. Not all state is automatically known. Some info costs money or effort (surveys, historical price data, analytics).

---

## L

**Labor.** Primitive 3. Time-bounded capacity to do work. Comes from players, hired NPCs, or AI agents. Located somewhere; must be where the work is.

**Land rush.** The opening period of a new shard when plots are claimed at high speed by early players.

**Law of the universe.** One of the 10 engine-enforced rules in `04_LAWS_OF_THE_UNIVERSE.md`. Distinct from a **pillar** (which is a design principle, not engine-enforced).

**LLM-driven agent.** See **Tier 3 agent**.

**Lua.** The embedded scripting language for the user-code layer (Phase 4+). Sandboxed, deterministic, resource-metered.

---

## M

**Market.** Primitive 7. Mechanism for exchanging goods, services, or capital. Two layers: order books (7b) for high-volume assets, P2P (7a) for the rest.

**Material.** Primitive 2. Physical stuff with properties (mass, density, conductivity, etc.). Has a quantity and a location. Conserved.

**Matter.** Synonym for material in casual usage. The formal primitive name is "Material."

**Mobile companion.** The iOS/Android app. Read-heavy, designed for 5 specific quick-action flows. Not a full game client.

**Movement.** Primitive 4 (in conjunction with Time and Distance). Moving goods, labor, or capital between locations takes time and may cost money.

---

## N

**NPC.** A non-player character. Almost always a Tier 1 or Tier 2 agent. In Realm, NPCs are functional (consumers, laborers, baseline suppliers) — they are not characters with personality. Personality-driven NPCs are **named agents** (Tier 3).

**Named agent.** A Tier 3 LLM-driven AI character with a persistent personality, memory, and storyline. Examples: Margaux the Industrialist, Rico the Speculator. Distinct from generic NPCs.

---

## O

**Optimizing agent.** See **Tier 2 agent**.

**Order book.** Primitive 7b. A public list of buy/sell orders for an asset. Emerges automatically when an asset hits a volume threshold.

---

## P

**Phase.** A discrete stage in the build plan (Phase 0 through Phase 7+). Each phase has a build list and a test gate. See `13_PHASED_TODO.md`.

**Phase test gate.** The pass/fail criterion that gates progression to the next phase. Skipping these is the single biggest risk to the project. Do not skip.

**Pillar.** One of the 7 design principles in `02_DESIGN_PILLARS.md`. Distinct from a **law** (engine-enforced) — pillars are guidance for design decisions, enforced by judgment.

**Plot.** Primitive 1. A bounded region of the world with intrinsic properties (terrain, climate, hidden subsurface) and derived properties (owner, improvements, surveys).

**Primitive.** An economic atom — an entity, resource, or capability the engine knows about natively. There are 9 in v1. See `03_PRIMITIVES_SPEC.md`. Players compose primitives into businesses; we don't pre-define the businesses.

**Production.** Primitive 6. A process that consumes inputs (matter, labor, energy, money) at a location over time and produces outputs (matter, services), governed by recipes.

**Public mode.** The persistent multiplayer mode. Many humans, real consequences, never pauses, slow real-time. See `05_GAME_MODES.md`.

---

## R

**Recipe.** A configured production process with declared inputs, outputs, throughput, and energy needs. Validates against conservation laws. Players choose from a recipe library; technically, anything physics-legal is a valid recipe.

**Reputation.** Primitive 9-adjacent / Law 7. A public, append-only summary of a party's contract history. Cannot be deleted or revised.

**Replay.** A reconstruction of past world events using a snapshot + event log. Possible because the engine is deterministic.

---

## S

**Sandbox.** The isolated execution environment for player-deployed code services. Restricts file/network access; meters CPU and memory.

**Scenario.** A configured starting world for solo mode (or a closed cohort). Defines the map, initial AI agents, starting conditions, and any optional objective. Examples: "Frontier," "The Cartel," "The Bootstrapper."

**Season.** A time-boxed multiplayer cohort, typically 90 days. Ends with rankings; world resets.

**Service.** A player-deployed code function in the user-code layer. Can be called by other players (paid via subscription or per-call). Has reputation, versioning, and metrics. Phase 4+.

**Shard.** A single instance of the multiplayer world. Independent economy. Multiple shards can run in parallel; each is its own world.

**Solo mode.** Single-player vs AI agents. Pausable, configurable speed, save/load. The existence test of the design.

**Subsurface composition.** The hidden material content of a plot. Not visible until surveyed. Part of the information-asymmetry design.

**Survey.** An action that reveals (some of) a plot's subsurface composition. Costs money and time. Can be performed by the plot owner or by surveyors hired under contract.

---

## T

**Tick.** The smallest unit of simulation time. The engine processes a fixed amount of work per tick (handle inbound actions, run scheduled events, tick agents, clear markets). Tick rate ≠ game-time rate; many ticks make up a game-day.

**Tier 1 agent.** Hand-coded behavioral NPC. Cheap, predictable, used in volume to populate the world. ~100 lines per archetype.

**Tier 2 agent.** Algorithmic optimizing NPC. Solves a defined problem (market-making, logistics, production planning). Provides credible mid-tier competition.

**Tier 3 agent.** LLM-driven named character. Has personality, memory, and natural-language messaging. Few per world (5–15) due to LLM cost. The story-generators of solo mode.

**Time scale.** Law 2. The fixed ratio between game-time and real-time. 1 game-day = 1 real-hour in public mode; configurable in solo.

**Transaction.** A double-entry-bookkept state change. The only legal way to mutate world state. Conservation laws are enforced at this layer.

**Transit.** State of goods that have been dispatched but not yet arrived. Visible to owner; cannot be used or sold while in transit.

---

## U

**User-code layer.** The Lua-based programmable services system. Players write code, deploy as services, sell to other players. Phase 4+. The "moat primitive."

---

## V

**Visibility.** A first-class concept (Law 6). Every piece of state has a "who can see this?" flag: public, owner-only, contract-revealed, etc.

---

## W

**World.** A single simulation instance. In solo, a save file. In multi, a shard.

**World-tick.** See **Tick**.

---

## Terms we deliberately don't use

A few words that come up in similar games but we avoid in Realm — partly to stay disciplined, partly because they imply mechanics we've rejected.

- **Quest.** No quests. The economy generates motivation; we don't script objectives.
- **Level.** No leveling. Skills exist on labor, but players don't have a "level."
- **Class.** No classes. Players are entrepreneurs; their identity emerges from their decisions.
- **Resource node.** Use **plot** + **subsurface composition** instead. "Node" implies a designer placed it; in Realm, world-gen produces it.
- **Faction.** Not in v1. Maybe in some future phase if player governance becomes a thing.
- **PvP.** No combat ever. Use **competition** for economic rivalry.
- **Grind.** If players say "this game has grind," something's wrong with the design — there should be no rote actions that aren't decisions.
- **Tutorial.** We have a guided first hour, not a tutorial. The distinction is real: a tutorial *teaches mechanics*; the first hour *introduces primitives via real play*.

---

## Adding terms

When a new term enters the design discussion, add it here before it gets used in three docs. Drift is cheap to prevent and expensive to fix.

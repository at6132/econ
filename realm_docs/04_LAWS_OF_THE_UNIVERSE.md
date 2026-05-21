# 04 — Laws of the Universe

> The "physics engine" of the economy. These laws are what keep the economy from collapsing, hyperinflating, or stagnating. They are enforced at the engine layer, not the application layer.

---

## Law 1 — Conservation

**Matter is conserved. Money is conserved.**

For every unit of material that exists, there's a record of where it came from (extracted from a plot, bought from another player). No material spawns from nothing. When material is consumed in production, it converts to other material per a recipe (with mass balance: outputs ≤ inputs, accounting for waste).

Money is the same. Every dollar in a player's account came from somewhere — initial grant, NPC seed transaction, payment from another account. There is no "free money" spawning anywhere outside designed channels.

**Engine implication:** All transfers of matter and money go through a single transaction layer that double-entry-bookkeeps the change. There is no path to mutate balances directly. Audit logs exist for everything.

**Designed exceptions (each one is intentional and bounded):**
- Initial player grant ($X starting capital, recorded as "system genesis").
- Scheduled NPC injections in solo mode (NPC consumers buy goods → money enters the player economy from NPC accounts; NPC accounts get topped up on a schedule).
- Decay & loss (matter and goods can be destroyed; money cannot).

---

## Law 2 — Time has scale

The simulation has a tick rate. Real-world time and game-world time are related by a fixed ratio.

**v1 proposal:** 1 in-game day = 1 real-world hour, in public mode. Solo mode is configurable (1:1, paused, or 4x faster).

**Why this ratio:** Slow enough that a player can dip in and out without missing critical events; fast enough that meaningful change happens within a single play session. A week of in-game time = ~7 hours real, roughly one work day of intermittent attention.

**Engine implication:** All movement, production, contract triggers, and decay are expressed in game-time units. The mobile companion app's job is partly to alert players when game-time-sensitive things happen.

**Pause behavior:**
- Solo mode: pausable.
- Public mode: never pauses. Tickets to "save points" or "reset" do not exist.
- Competitive seasons: never pause within a season; the season itself ends and resets.

---

## Law 3 — Distance has cost

Moving anything between two locations takes time and may cost energy/money.

**Movement cost function (rough):**
```
cost = base_rate × distance × (1 + load_factor) × terrain_modifier
time = distance / speed × terrain_modifier
```

Where speed depends on transport asset. A coastal vessel is fast over water but useless inland. A truck is slow but flexible.

**Engine implication:** Goods in transit are tracked in a "transit" state with arrival time. Players can see in-transit inventory but cannot use or sell it until it arrives.

---

## Law 4 — Energy is required

Production consumes energy. **Delivered electricity** is a **regional grid service** billed in **kWh** (watt-hours), not a warehouse commodity. **Fuel** (coal, charcoal, etc.) remains tradeable matter used to **generate** exports into the grid. **Stored electrical energy** exists only in **battery** buildings on a plot.

**Engine implication:** Recipes specify an `energy_wh` draw from the connected grid or on-site batteries. If the grid is at capacity (brownout) and batteries are empty, production stalls. Generators and fuel supply are foundational verticals.

**Important sub-law: regional energy networks.** Power does not transmit globally for free. Road-connected **grid regions** clear price daily; a **utility operator** issues periodic statements. A region without generation is economically constrained until someone builds capacity.

---

## Law 5 — Things decay without maintenance

Buildings, vehicles, equipment, and stockpiles deteriorate over time without upkeep.

**Decay rates:**
- Stored perishables (food, organics): fast decay if not refrigerated/preserved
- Buildings: slow decay (need periodic maintenance contracts or labor)
- Equipment: moderate decay, accelerated by use
- Vehicles: similar to equipment
- Code/services: do *not* decay (logic doesn't rust) but require periodic CPU payment to remain hosted

**Engine implication:** Decay creates ongoing demand for maintenance services and replacement materials. It also prevents passive infinite-rent strategies — you can't just claim a plot, build a factory, and walk away forever.

**Important:** Decay is one of the things players will most want to escape. We must resist offering "permanent buildings" or "auto-maintenance subscriptions priced at zero." Decay is what keeps the game alive.

---

## Law 6 — Information has cost

Not everything is automatically known.

**What's free / public:**
- World geography (terrain, coastlines, plot boundaries)
- Plot ownership (who owns what)
- Public order books (current prices, recent trades)
- Reputation summaries (contracts honored / breached, with delay)
- A player's declared business profile (if they choose to publish)

**What costs effort or money:**
- Subsurface composition of a plot (must survey or buy survey data)
- Other players' private inventories
- Other players' private contract terms
- Historical price data beyond the recent window (sold as analytics products)
- Forecasts, indices, and synthesized data (sold by analytics firms)

**What is hidden by design:**
- Other players' private accounts (unless a contract reveals them)
- Code internals (a service's behavior is observable, but its source is private unless published)
- AI agent strategies (in solo mode)

**Engine implication:** Visibility is a first-class concept. Every piece of state has a "who can see this?" flag. Markets for information (analytics, surveys, forecasting) emerge naturally because hidden info is real.

---

## Law 7 — Reputation accumulates

Every player and business has a public reputation profile.

**What's tracked:**
- Contracts entered (count)
- Contracts honored (count)
- Contracts breached (count + severity)
- Average payment punctuality
- Average delivery punctuality
- Notable disputes (resolved how)
- Optional: self-published narrative (a "company description")

**Engine implication:** Reputation is a public read-only object on every account. It cannot be deleted or revised. Players can create new identities (with cost — see Law 8), but they cannot launder old ones.

---

## Law 8 — Identity has cost

Creating a new player identity in the same world has a meaningful cost (limit on free identities, cooldown periods, optional verification gates for premium features). This prevents reputation laundering and account farming.

**v1 design:** One free account per real human (light verification). Additional accounts allowed but flagged and may have reduced access.

**Public mode:** Stricter than solo. Closed-cohort competitions: hand-curated, no farming possible.

---

## Law 9 — Determinism

Given the same starting state and the same player/agent inputs, the simulation produces the same outputs. Always.

**Why:** Reproducibility for debugging. Replays. Offline simulation. Solo-mode save/load. Cheating prevention.

**Engine implication:** All randomness derives from a tick-stamped seed. Player code must be deterministic. Side effects go through the engine's transaction layer.

---

## Law 10 — The simulation is authoritative

The state of the world is what the simulation says it is. Player code, third-party tools, and clients (web/mobile) only *propose* actions. The engine validates and either commits or rejects.

**Engine implication:** No client-side trust. The mobile app and web client are dumb terminals on top of the simulation. Cheating is structurally impossible because the engine never accepts unverified state.

---

## How these laws hold together

Laws 1, 4, 5 prevent the economy from blowing up (no infinite money, no infinite production, no permanent assets). Law 2 makes everything time-bounded. Law 3 makes geography matter. Laws 6–8 create information markets and trust dynamics. Laws 9–10 make the engine reliable and uncheatable.

If you find yourself wanting to violate one of these laws to make a feature easier — *don't.* Either the feature is wrong, or the law needs revision (and revising a law is a major design event, not a casual fix).

---

## Common temptations to violate laws (and what to do instead)

- **"This feature would be simpler if money could be created here."** No. Find the real source of money in the design. Probably it's an NPC payment or a contract trigger.
- **"This feature would be simpler if buildings didn't decay."** No. Either accept decay or expose decay-cost as a service that players can buy.
- **"This feature would be simpler if information were public."** Maybe. Audit whether making it public removes a market. If it does, keep it private.
- **"This feature would be simpler if travel were instant."** No. Geography is a pillar.
- **"This feature would be simpler if the simulation paused."** Solo only. Public mode never pauses.

When in doubt, the simpler-feature path is usually the wrong one. The constraints are what make the game.

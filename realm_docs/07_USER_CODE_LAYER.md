# 07 — The User Code Layer

> This is the moat. No other game in this genre has it. Players write code that runs in the world and sell it as a service to other players. This is what turns Realm from "an economy sim" into "a platform on which players build economic infrastructure."

---

## The pitch

A player wants to automate their inventory management → they write a script that watches their inventory and places orders. **That's a script.**

A player notices other players have the same problem → they polish the script, add a UI, and offer it as a subscription service. **That's a SaaS.**

Other players subscribe → there's now a real business that exists entirely as code, with revenue, customers, and reputation. **That's a tech company.**

Multiply across thousands of services and you get a real software industry inside the game. Logistics services. Analytics services. Credit-scoring services. Trading bots. Insurance policies. News aggregators. Whole genres of business that exist only in code.

**This is the same dynamic that made Roblox a $40B company** — UGC where users build things other users pay for. But Realm has a tighter loop because every transaction is real (in-game) money tied to a real economy.

---

## Design principles for this layer

1. **Safe.** Code cannot crash the simulation, exhaust resources without payment, or escape its sandbox.
2. **Useful.** The API must be expressive enough to build real services. A trading bot must be possible. A logistics optimizer must be possible. An analytics dashboard must be possible.
3. **Teachable.** A motivated player with no programming background should be able to build something simple within a week.
4. **Costly.** CPU, memory, and storage cost in-game money. Free hosting breaks the economy.
5. **Composable.** A service can call another service. This is what allows ecosystems to form.

---

## v1: the language(s)

Two interfaces, one runtime. Both compile down to the same bytecode/instructions.

### Interface A: visual block-based programming
Scratch-style. Drag-and-drop blocks. "When inventory < X, place buy order at Y." Suitable for non-programmers. Covers ~70% of common automations.

### Interface B: text-based scripting language
Lua (recommended). Familiar, sandboxable, well-understood, fast. The block language compiles to the same Lua runtime.

**Why Lua and not a custom language:**
- It's already sandboxable
- It's already fast
- Players who know other languages can learn it in a day
- We don't waste innovation budget on syntax design — we spend it on the API and the platform

**Why not a custom language:**
- We have a thousand more important things to design
- Custom languages have a high learning cost and questionable upside
- Future option: if there's a reason to add a custom language *later*, we can. But not v1.

---

## The API surface

This is the actual hard design work. What can code do?

### Read-only API (free or cheap)

- `world.time()` — current game-tick
- `world.geography()` — read map, plots, terrain (public info)
- `market.book(asset)` — read order book for an asset (subject to delay if info-cost is enabled)
- `market.history(asset, range)` — historical prices (cost scales with range)
- `me.inventory()` — your own inventory
- `me.accounts()` — your own accounts
- `me.contracts()` — your contracts
- `reputation.of(party_id)` — public reputation summary
- `messages.inbox()` — your messages

### Write API (consumes resources, may cost money)

- `market.place_order(asset, side, qty, price, expiry)`
- `market.cancel_order(order_id)`
- `contracts.propose(template, params, counterparty)`
- `contracts.accept(proposal_id)`
- `contracts.terminate(contract_id)`
- `messages.send(party_id, text)`
- `services.call(service_id, args)` — call another player's service
- `me.transfer(account, amount)` — move money between your own accounts

### Service-creation API (deploying your own service)

- `service.define(name, handler_fn, pricing_model)`
- `service.publish(service_id, listing_metadata)`
- `service.unpublish(service_id)`
- `service.metrics(service_id)` — your service's usage data

---

## Resource model

Code costs CPU, memory, and storage. Players pay for these in in-game currency.

**CPU budget:**
Each player has a base monthly allocation (free for everyone). Beyond that, you buy more from the engine at a market rate. Tier 3 / large operators may run dedicated nodes (paid).

**Memory:**
Code can persist data (a key-value store per service). Storage costs in-game money per byte per game-day.

**Determinism budget:**
Code must execute within a fixed instruction budget per call. Over budget = the call fails. This is what prevents one player's bad code from stalling the simulation.

**Why metering matters:**
Without a real cost, a player would deploy a million bots and run them for free. Resource costs make compute a finite, tradeable resource.

---

## Code as a business

A service is a deployed function with:
- A name and description (visible in a service marketplace)
- A pricing model (per-call, subscription, free, custom)
- An owner (the deploying player)
- A revenue stream (payments flow to the owner's account)
- Reputation (uptime, response quality, customer reviews)
- Versioning (services can be updated)

**Service marketplace:**
A built-in directory in the game where players browse, search, subscribe to services. Like an in-game app store.

**Discovery:**
- By category (analytics, logistics, automation, finance)
- By reputation
- By price
- By popularity
- By word-of-mouth (services other players use)

---

## Worked examples

### Example 1: Auto-restock script (block-based, beginner)

```
WHEN my inventory of "iron_ore" < 100
DO
  PLACE buy_order
    asset: "iron_ore"
    quantity: 200
    price: market.bid("iron_ore") + 5%
    expiry: in 1 game-day
END
```

Player runs this for themselves. Could publish it as a free template for other players to copy.

### Example 2: Logistics optimizer (Lua, intermediate)

```lua
-- service: optimal_route_v1
function on_call(args)
  -- args = { deliveries = [{from, to, qty}, ...], vehicles = [...] }
  local plan = solve_vehicle_routing(args.deliveries, args.vehicles)
  return plan
end

service.define("optimal_route_v1", on_call, { per_call = 50 })
service.publish("optimal_route_v1", {
  category = "logistics",
  description = "Computes optimal delivery routes for shipping companies. Saves you 10–30% on fuel.",
  price = "50 per call"
})
```

A shipping company calls this once a day to plan its routes. Pays 50 per call. The optimizer's owner makes ongoing revenue.

### Example 3: Market-making bot (Lua, advanced)

```lua
-- service: market_maker_iron
function tick()
  local mid = market.mid("iron_ore")
  local spread = me.config().spread_pct
  local size = me.config().order_size

  market.cancel_all()
  market.place_order("iron_ore", "buy",  size, mid * (1 - spread))
  market.place_order("iron_ore", "sell", size, mid * (1 + spread))
end

service.define("market_maker_iron", tick, { tick_every = 600 })  -- every 10 game-min
```

Owner runs it for themselves, profiting from spread. Or sells access ("rent the bot for X per day").

### Example 4: Credit scoring service (Lua, advanced)

```lua
function on_call(args)
  local rep = reputation.of(args.party_id)
  local contract_history = rep.contracts_recent(180)
  -- compute score based on contract honor rate, payment punctuality, etc.
  return { score = compute_score(contract_history), confidence = 0.85 }
end

service.define("credit_score_v2", on_call, { per_call = 10 })
```

Banks pay 10 per query. Bank A subscribes for 100 queries/day = 1000/day in revenue.

---

## What code *cannot* do

- Cannot read another player's private state.
- Cannot impersonate another player.
- Cannot create money or matter from nothing.
- Cannot bypass the contract system.
- Cannot make other players' code run.
- Cannot interact with external networks (no real-world HTTP).
- Cannot use real randomness (only the simulation's tick-stamped seed).
- Cannot consume more resources than budgeted.

These are enforced at the runtime layer, not by convention.

---

## Anti-abuse and platform health

People will abuse this. Plan for it.

**Likely abuse vectors:**
- **Wash-trading services** — services that pretend to provide value but mostly trade with themselves.
  - Mitigation: reputation scoring, market surveillance, public review system.
- **Spam services** — flood the marketplace with low-quality services.
  - Mitigation: deployment fee, listing fee, search quality.
- **Malicious services that scam users** — service collects subscription fee and does nothing.
  - Mitigation: reputation, public reviews, optional escrow for subscriptions.
- **Resource exhaustion attempts** — code that tries to crash the simulation.
  - Mitigation: hard CPU limits, instruction budgets, automatic service termination on overrun.

**Moderation:**
We do *not* moderate the *quality* of services. The market sorts that out. We *do* moderate technical abuse (resource exhaustion, security bypass).

---

## Build order

This system is **not v1.** It is the largest single chunk of post-v1 work.

- **Phase 4 in the TODO** — first version of the user-code layer.
- **Phase 4.5 / 5** — block-based interface, marketplace, polish.

But — and this is important — **the engine architecture in v1 must not preclude this layer.** The simulation API, the data model, and the contract system all need to be designed knowing that user code will eventually attach to them. We don't build the layer in v1. We don't make v1 architecture decisions that block the layer in v3.

Specifically:
- The simulation's internal API for taking actions must be cleanly factored so a Lua sandbox can call it.
- The contract system must be expressive enough that "service subscription" is a real contract type.
- The reputation system must work for businesses (not just human players).
- The data layer must support per-service storage with quotas and billing.

---

## Why this is worth the difficulty

This is the feature that makes Realm a *platform* instead of a *game*. Roblox and Minecraft are billion-dollar businesses because users build content for users. Realm with a user-code layer is the same dynamic, but for *economic* content.

Without it, Realm is "another economy sim, slightly better than the rest."
With it, Realm is "the platform on which players build the digital businesses of a fictional world." That's a category of one.

It's also the feature most aligned with your existing strengths — agent design, sandboxing, programmable systems. Lean into it.

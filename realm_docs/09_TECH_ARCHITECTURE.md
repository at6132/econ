# 09 — Technical Architecture

> The "how it actually gets built" doc. Stack, services, data model, scaling plan. Designed so v1 is shippable solo, v2+ adds multiplayer cleanly without re-architecting.

---

## Architecture overview

Realm is structured as **simulation + services + clients.**

```
┌────────────────────────────────────────────────────┐
│                    CLIENTS                          │
│  Web (Next.js + React)   Mobile (React Native)      │
└──────────────┬───────────────────────┬──────────────┘
               │                       │
               ▼                       ▼
┌────────────────────────────────────────────────────┐
│                  API GATEWAY                        │
│  REST + WebSocket. Auth. Rate-limit. Validation.    │
└──────────────────────┬─────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌────────────┐ ┌──────────────┐
│  SIMULATION  │ │  AGENT     │ │  USER-CODE   │
│  ENGINE      │ │  RUNTIME   │ │  RUNTIME     │
│  (auth.)     │ │  (Tier 1/2 │ │  (Lua sandbx │
│              │ │   /3)      │ │   per service│
└──────┬───────┘ └─────┬──────┘ └──────┬───────┘
       │               │               │
       └───────────────┼───────────────┘
                       ▼
┌────────────────────────────────────────────────────┐
│                  DATA LAYER                         │
│  Postgres (state)   Redis (hot)   S3 (history/blobs)│
└────────────────────────────────────────────────────┘
```

The **simulation engine is authoritative.** It is the only thing that can mutate game state. Everyone else (agents, code, clients) submits *proposed actions*; the engine validates and commits or rejects.

---

## v1 stack (solo mode)

For solo mode, you can collapse this whole architecture into a single web app + simulation worker. No need for distributed systems until multiplayer.

| Concern | v1 choice | Rationale |
|---|---|---|
| Web frontend | Next.js + React + TypeScript | Standard, fast iteration, great tooling |
| 2D map rendering | Pixi.js (Canvas/WebGL) | Performant 2D, works in browser, mature |
| Charts / data viz | Recharts or D3 | Standard for trading-style UIs |
| Backend / API | Node.js + TypeScript (or Python — see note) | Whatever you'll iterate fastest in |
| Simulation engine | **Python** (initial), Rust later if needed | Python = fastest design iteration |
| Database (state) | SQLite for solo, Postgres for multi | SQLite is fine for a single-player save file |
| In-process cache | Redis (multi only) or in-memory (solo) | Solo doesn't need it |
| Mobile | React Native + Expo (TypeScript) | Codeshare with web where possible |
| User-code sandbox | Lua via lupa or wasmtime+Lua | Standard, sandboxable |
| LLM agents | Anthropic API (Claude) | You're an Anthropic-aligned dev; obvious choice |

**On the simulation language choice:** Python is fast to iterate but slower to run. For v1 (solo, ~50 plots, ~15 agents), Python is fine. If you eventually need 1000+ concurrent players in a shard, you'll want to rewrite the hot path in Rust or Go. **Don't optimize prematurely.** Ship solo in Python.

**On the language for the API layer:** if Python is doing the simulation, putting the API in Python (FastAPI) keeps the stack uniform. If you prefer Node, that's fine too — just commit and don't rewrite.

---

## v2+ stack (multiplayer)

When you add multiplayer, the system splits more cleanly:

- **Simulation engine** becomes its own service (1 process per shard, possibly multi-threaded).
- **API gateway** is its own service (Node or Python, fronts WebSockets and REST).
- **Agent runtime** is its own service (manages Tier 1/2/3 agents).
- **User-code runtime** is its own service or set of workers (per-service sandboxes).
- **Postgres** is the source of truth.
- **Redis** is the hot cache for prices, agent state, etc.
- **S3 (or equivalent)** for historical data, replay logs, large blobs.
- **Object storage** for player code artifacts (versioned).

You can run all of this on a few servers initially. As shard count grows, you horizontally scale by shard.

---

## The simulation engine

The heart of the project. Designed as a **deterministic tick-based system.**

### Tick loop

```
while world.running:
    tick_start = now()
    
    # 1. Process inbound actions (from players, agents, code)
    for action in pending_actions_queue:
        if validate(action):
            apply(action)  # mutates state in transaction
        else:
            reject(action)
    
    # 2. Run scheduled events (contracts triggering, decay, etc.)
    process_scheduled_events(world.time)
    
    # 3. Tick AI agents (Tier 1 every tick, Tier 2 every N ticks, Tier 3 on slower cadence)
    tick_agents(world.time)
    
    # 4. Tick user code services (those with `tick_every` schedules)
    tick_services(world.time)
    
    # 5. Run market clearing (match limit orders, update last-trade prices)
    clear_markets()
    
    # 6. Advance world time
    world.time += 1
    
    # 7. Persist snapshot if needed (every N ticks)
    if world.time % SNAPSHOT_INTERVAL == 0:
        persist_snapshot()
    
    # 8. Sleep until next tick
    sleep_until(tick_start + TICK_DURATION)
```

### Tick rate

Public mode: 1 game-day = 1 real-hour, but ticks happen much more often (e.g., 1 game-minute per tick = 1 real-second per tick = 1440 ticks per game-day).

This gives smooth real-time-ish gameplay without forcing the engine to tick at 60Hz.

Solo mode: tick rate is configurable per save (1x, 2x, 4x, paused).

### Determinism

Critical: same starting state + same inputs = same outputs.

- All randomness derives from `(world.tick, randomness_purpose)` seeds.
- Wall-clock time is never used inside game logic.
- Agent decisions, price formation, and decay all use deterministic functions.
- This makes replays, debugging, and offline simulation possible.

---

## Data model (sketch)

Tables / collections (Postgres-style, adapt to your data store):

- `worlds` — one row per shard / save file
- `players` — one per human player
- `accounts` — financial accounts (player-owned, business-owned, system-owned)
- `plots` — one per plot, includes ownership, terrain, hidden subsurface
- `surveys` — survey results, who knows what about which plot
- `inventories` — material holdings, indexed by owner + location
- `materials` — material catalog
- `production_units` — built infrastructure on plots
- `labor_pools` — regional labor markets
- `employments` — active employment relationships
- `orders` — open buy/sell orders on order books
- `trades` — historical executions
- `contracts` — active contracts (template + parameters + state)
- `contract_events` — payment, delivery, breach events
- `messages` — player-to-player and agent-to-player messages
- `services` — user-deployed code services
- `service_subscriptions` — who subscribes to what
- `service_calls` — call logs for billing
- `agents` — AI agent records
- `agent_memories` — Tier 3 memory blobs
- `reputation_events` — auditable reputation history

Key principle: **every state change is a transaction.** No direct mutations. The transaction layer is what enforces conservation laws.

---

## Real-time updates

The web client and mobile client need to react to changes:

- New order on an order book → push to subscribers
- Contract proposed → push to counterparty
- Agent message → push to recipient
- Price tick → push to chart subscribers

**v1:** WebSocket connection from client to API gateway. Server pushes events on change. Client subscribes to topics it cares about (e.g., "prices for material X," "my contracts," "my account").

**Mobile:** Same WebSocket model. Plus push notifications for high-priority events (new contract proposal, contract deadline approaching, large price move) — even when app is closed.

---

## The user-code runtime

Each deployed service has its own sandbox with:
- A Lua interpreter (with restricted standard library)
- A connection to the simulation API (read/write actions)
- A storage allocation
- A CPU budget per tick or per call
- An execution history (for debugging and audit)

When a service is called:
1. The runtime instantiates a sandbox with the service's code
2. Validates the caller's permission (subscription / payment)
3. Runs the code with the call args
4. Captures any actions the code attempts (via the API)
5. Commits actions (subject to engine validation) and returns the result
6. Bills CPU usage to the service owner's account

**Security:** Lua sandboxing is done via wrapping the interpreter, restricting global access, and using OS-level isolation if needed. Services cannot access the file system, the network, or other services' state.

---

## Mobile companion architecture

The mobile app is intentionally simple: a thin client over the API.

- React Native + Expo for cross-platform iOS/Android.
- Authenticated via the same auth as web.
- Subscribes via WebSocket to alerts and key data.
- Push notifications for time-sensitive events.
- Most "complex" actions (build, code, etc.) are gated to the web client — the mobile UI just shows "open in web" for those.
- Fully read-capable (markets, news, accounts, contracts) and write-capable for quick actions (place orders, accept/reject contracts, send messages).

**No mobile-specific game logic.** The mobile client is a UI over the same API the web client uses.

---

## Auth and identity

- v1 (solo): no auth needed for offline solo. Save files local. Optional account for cloud saves.
- v2+ (multiplayer): standard email + password, with optional OAuth (Google, Apple). Possibly later: identity verification (KYC-lite) for premium tiers or competitive seasons.

---

## Persistence strategy

**Solo mode:**
- Save files are SQLite files. One save = one file. Easy to copy, share, back up.
- Cloud sync optional via account.

**Public mode:**
- Postgres is source of truth.
- Periodic snapshots (full state dumps) for disaster recovery.
- Append-only event log for everything that happened (used for replays, audits, customer support).

**Replay:** since the engine is deterministic, you can replay a world from snapshot + event log. Useful for debugging, cheating investigations, and content (commentary on past events).

---

## Performance targets

For v1 solo:
- 50 plots, 15 agents, ~100 active orders → tick in <50ms on a mid laptop.
- 10K materials in inventory total → no problem in Python.

For v2 multiplayer (per shard):
- 500 plots, 200 agents (mostly T1), 100 human players, 10K active orders → tick in <500ms on a single server.
- This is achievable in Python with care, but Rust/Go would handle it more comfortably.

For v3+ scale:
- 5K plots, 1K humans → almost certainly needs the hot path in Rust.
- Multiple shards, each independent.

---

## Observability

From day 1, instrument everything:

- Structured logs for every action accepted/rejected
- Metrics: tick duration, action throughput, market depth, active services
- Tracing for slow ticks
- Audit log for any state change (immutable)

This is essential because the most interesting bugs in this kind of game are *emergent economic dysfunctions*, and you can only diagnose those with good observability.

---

## Decisions to revisit

These are open questions to leave for later, but flag now:

1. **Simulation language for v3.** Python now, possibly Rust later. Don't decide yet.
2. **Single-shard vs multi-shard architecture.** Probably multi-shard. Defer to v2.
3. **Currency model — single vs player-issued.** Single in v1, revisit for v2+.
4. **User-code language — Lua vs alternatives.** Lua in v1. Consider WASM-based options later.
5. **Hosting / deploy.** Vercel + Railway or Fly.io for v1. AWS / GCP later if needed.

The list of "decisions deferred" is healthy. Many architecture failures come from making these too early.

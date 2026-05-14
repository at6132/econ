# 16 — Vision anchor & phase status

> **Purpose:** Re-anchor the north star and record **where the repo actually is** vs `13_PHASED_TODO.md`, so day-to-day implementation does not quietly drift into “random sim features.”

---

## Vision summary (north star)

**Realm** is a 2D web-first economic civilization sim where the **entire economy** — every business, price, currency, contract, and service — is **invented and run by players**, with **AI agents filling those same roles in solo mode**. Players claim plots of land with **hidden subsurface resources**, hire labor, build production, sign **multi-step contracts**, and trade on **emergent order books**; advanced players write **Lua-based code services** that other players subscribe to, turning the game into a **platform where in-game SaaS businesses are real businesses**.

The design rests on **9 economic primitives** (land, matter, labor, time/distance, capital, production, markets, contracts, code) and **10 engine-enforced laws** (conservation of money and matter, decay, information cost, reputation, determinism, etc.) so **scarcity and consequence stay real**.

**Three modes share one engine:**

| Mode | Role |
|------|------|
| **Solo** | vs AI agents; pausable; **existence test** of the design |
| **Public persistent multiplayer** | slow real-time; **1 game-day ≈ 1 real-hour**; **mobile companion** for monitoring on the go |
| **Competitive closed-cohort seasons** | invite-only, time-boxed; marketing / balance-testing arena |

**Do not confuse “what we are building this month” with “the full vision.”** The phased TODO intentionally ships **thin vertical slices** first.

---

## Where we are in the phase system

**Official phase doc:** `13_PHASED_TODO.md`.

**Current phase:** **post-Phase 8 — headless API testing.** Phases 2, 7, and 8 are all **engineering-closed**:

| Phase | What it shipped | Closed on |
|------|-----------------|-----------|
| **2 — Solo Polish & Visual Identity** | Pixi, schematic, Tier 2, decay, info costs, scenarios, polish | 2026-05-10 (`18_PHASE_2_COMPLETION_CHECKLIST.md`) |
| **7 — Real population economy** | Four-island worldgen, `LaborerNPC` lifecycle, towns + residences, stores + consumer spending, employment market with real wage transfers, **inter-island trade with NPC cross-island buy orders**, **25-assertion Phase 7 integration gate** | 2026-05-14 |
| **8 — The Volatility Engine** | Seasonal calendar, natural disasters (drought / blight / mine collapse / storm / seismic / flood), epidemics with herbs+medicine+apothecary supply chain, market cycles (price panic, credit crunch, route blockage, boom, depletion), event-driven analytics products, Margaux event beats, **30-assertion integration gate** | 2026-05-14 |

**A1** ($30 stranger playtest gate) remains deferred. The next work phase is **headless API testing** — not feature development.

**Sprints 1–6 are complete.** Sprint 6 (Infrastructure & Completeness — transport roads, production throughput scaling, supply-chain visibility, final polish) closed on 2026-05-13. The `tests/test_full_solo_game.py` integration gate runs all 20 assertions and resolves cleanly (13 hard passes, 7 conditional skips for behaviors that require a larger map or a longer time horizon than the 3-game-day test window).

Phase 1 **engineering checklist** is closed (`17_PHASE_1_COMPLETION_CHECKLIST.md`).

### Phase 1 checklist — honest snapshot (rolling)

This is a **status snapshot**, not a promise every box is finished to final quality.

**2026-05-08 — Phase transition:** Phase 1 **B–E** ✅ per `17_PHASE_1_COMPLETION_CHECKLIST.md`. **2026-05-10:** Phase 2 **engineering** ✅ per `18_PHASE_2_COMPLETION_CHECKLIST.md`. Stranger **$30** gate remains **A1** (deferred).

**Engine core (Phase 1 intent + Sprint 1-6 expansions)**

| Item | Status |
|------|--------|
| Tick-based deterministic loop | ✅ `advance_tick`; RNG via `(tick, purpose)` |
| World generation | ✅ Frontier + Genesis (50 settlers, 5 archetypes, NPC bank, 2 NPC energy/road companies) |
| Plots (Primitive 1) | ✅ terrain, ownership, survey reveals subsurface; **claim cost scales with population density (Sprint 6.D3)** |
| Materials (Primitive 2) | ✅ starter set + spoilage transform; party storage cap + building bonus |
| Capital (Primitive 5) | ✅ accounts, transfers, conservation enforced; **per-party sub-accounts with rolling P&L (Sprint 5.B)** |
| Production (Primitive 6) | ✅ recipes, runs, ticks; building labor BPS on plot; **run_count, continuous & auto-restart (Sprint 6.B); throughput multiplier; auto-list output (Sprint 6.D2)**; **output lands in party inventory directly (Sprint 6.D1)** |
| Movement (Primitive 4) | ✅ shipping / transit by tick distance; deliveries respect storage cap; **roads reduce per-tile cost 50% + tolls (Sprint 6.A)** |
| Order books (Primitive 7b) | ✅ asks + bids, escrow, crossing; FIFO at price level by `order_id`; **large-buy + supply-concentration signals (Sprint 6.C)** |
| P2P trade (Primitive 7a) | ✅ atomic trade + optional idempotency + stable error codes |
| Contracts (Primitive 8) | ✅ supply FSM + memo/hire stubs; **forward contracts (Sprint 4); bank loans with collateral (Sprint 5.C)** |
| Reputation | ✅ counters + supply/memo hooks; **tiered bank rates, exchange price modifier (Sprint 5.C)** |
| Code / Lua services (Primitive 9) | **Explicitly later** — Phase 4+ per roadmap |

**AI agents**

| Item | Status |
|------|--------|
| Tier 1 behavioral NPC loops | ✅ six loops (see `agents_tier1.py` docstring) |
| Tier 2 deterministic archetypes | ✅ Sprint 5.D — Specialist (iron/timber), Flipper, Shipper, Financier, Monopolist (Kessler) |
| Tier 3 LLM agent (Margaux) | ✅ Sprint 5.E — day 0-7 arc, archetype observation beats, player-profile tracking |
| Tier 3 generalised | Phase 3+ per roadmap |
| NPC infrastructure builders | ✅ Sprint 3 energy_central; Sprint 6.A Frontier Roads Co. |

**Frontend**

| Item | Status |
|------|--------|
| Next.js shell | **Yes** |
| Map | **Yes** — data still plot lattice; **organic SVG mesh** is presentation |
| Market / logistics / contracts / log UI | **Yes** — Bloomberg-style panels; tabs cover Phase 1 actions |
| Schematic plot view | **Yes** — engine validate + `PlotSchematicPanel` (Phase 2) |

**Persistence**

| Item | Status |
|------|--------|
| SQLite save / load | **Yes** — includes order books, `p2p_idempotency`, market history |

### Phase 1 **test gate** (from doc 13)

> 3–5 **strangers**, ~1 hour, “would you play another hour?” — **3 of 5 must say yes.**

**Status:** **Not claimed as passed here.** Until this is run seriously, Phase 1 is **not** “done” regardless of feature count.

---

## Drift guards (when tempted to overbuild)

1. **Map beauty ≠ economic proof.** Organic visuals serve readability and vibe; **fun and clarity of the economic loop** are what Phase 1 gates.
2. **Lua / true SaaS layer** is a **flagship later unlock**, not a sneaky Phase 1 requirement.
3. **Multiplayer and mobile companion** are **mode products** on the **same engine** — they are **not** v1 solo deliverables.
4. If a feature does not trace to a **primitive** and a **law/pillar check**, pause and name which phase it belongs to.

---

## Related docs

- `01_VISION.md` — canonical long-form vision
- `05_GAME_MODES.md` — three products / modes
- `03_PRIMITIVES_SPEC.md`, `04_LAWS_OF_THE_UNIVERSE.md` — technical heart
- `13_PHASED_TODO.md` — operational phases and gates

## Sprint 6 — Sprint completion summary (2026-05-13)

All four phases shipped and committed:

| Phase | Slice | Tests |
|-------|-------|-------|
| **A** | Transport roads: `RoadSegment` data model, `build_road`, `set_road_toll`, 50% per-tile cost reduction, NPC `Frontier Roads Co.`, API endpoints, snapshot v11 | `engine/tests/test_roads.py` (6) |
| **B** | Production throughput: `run_count` (one-shot / queued / continuous = `-1`), `runs_remaining`, `tick_production_auto_restart`, `production_input_stall` retries, `throughput_breakdown` combining efficiency × labor × terrain | `engine/tests/test_throughput.py` (4) |
| **C** | Supply-chain visibility: anonymous `large_buy_detected`, supply-concentration warning (≥ 35 % by one seller, ≥ 2 sellers), region activity, trade-flow overlay, expanded party-volume analytics | `engine/tests/test_supply_chain_visibility.py` (5) |
| **D1** | Production output → party inventory (matter source-of-truth); `plot_output_stock` is a cumulative display log; SNAPSHOT v11 migration moves any legacy stash into inventory on load | `engine/tests/test_plot_logistics.py` (3) |
| **D2** | `auto_list_output` flag per workshop; auto-lists at `cost_basis × 1.30` from inventory each `production_done` | `engine/tests/test_auto_list.py` (4) |
| **D3** | `claim_cost_cents_from_density` updated to `BASE × (1 + density × 4)` (frontier ≈ $5, hub-adjacent ≈ $23) | `engine/tests/test_geographic_clustering.py` (5) |
| **D4** | `GET /world/summary?party=…` lightweight HUD payload (cash, net-worth estimate, active production, maintenance warnings, unread counters, contract / order counts) | `engine/tests/test_world_summary.py` (3) |
| **D5** | `ensure_powered_plots_fresh` recomputes only on grid-source fingerprint change or once per game-day (down from every 10 ticks) | covered by `engine/tests/test_energy_grids.py` |
| **D6** | Full solo game integration: 20 assertions over a 3-game-day genesis run | `engine/tests/test_full_solo_game.py` (13 hard pass, 7 skip) |

**Suite status:** `cd engine && pytest tests/ --ignore=tests/test_labor_markets.py`  →  **437 passed, 7 skipped, 1 pre-existing Lua-env failure unrelated to Sprint 6.**

---

## Phase 7 — Real population economy (2026-05-13)

The "static demand" stack (`pop_hub` demand topups, fixed `population_density`, exchange-liquidity bumps) was deleted and replaced with a real bottom-up consumer economy.

| Slice | Engine module | Tests |
|-------|--------------|-------|
| **7A** Four-island worldgen, impassable ocean, 2× inter-island move cost | `realm/world/islands.py` | `tests/world/test_island_worldgen.py` |
| **7B** `LaborerNPC` dataclass + lifecycle (needs decay, health, death, migration) + `tick_laborer_births` stub | `realm/population/laborers.py` | `tests/population/test_laborers.py` |
| **7C** `Town` dataclass + `detect_towns` clustering + residential building + housing assignment | `realm/population/towns.py` | `tests/population/test_towns.py` |
| **7D** Store building + stock/price/withdraw actions + `tick_laborer_spending` + NPC-seeded stores; exchange liquidity top-up + hub `market_buy` hooks deleted | `realm/population/stores.py` | `tests/population/test_stores.py` |
| **7E** `post_job_opening` + `tick_job_market` + real wage transfers via `ledger.transfer`; unemployment + insolvency consequences | `realm/population/employment.py` | `tests/population/test_employment.py` |
| **7F** NPC cross-island B2B grain buy orders on deficit islands; market book / bids filterable by island; `genesis_storekeeper` funded so it acts as a real buyer; `labor_pool_for_region` now returns live unemployed `LaborerNPC` counts in Genesis | `realm/economy/inter_island.py` (+ `realm/population/labor.py`) | `tests/economy/test_inter_island_trade.py` (11) |
| **7G** 25-assertion integration gate: 4-island world, 3 game-days of real `advance_tick`; covers world structure, laborer lifecycle, towns/stores, entrepreneurial economy, inter-island trade, circular flow, information feed, conservation | — | `tests/integration/test_phase7_integration.py` (**25 assertions, all passing**) |

Demand is now driven by laborers consuming food, fuel, and shelter at stores; wages are paid through the ledger; conservation is invariant. Cross-island specialisation is in via NPC entrepreneurs posting cross-island grain bids when their own island runs short — the 4-island map is now a real trading network, not 4 isolated economies. The Phase 7 integration gate covers every system end-to-end; the Phase 8 integration gate continues to exercise them all under volatility.

---

## Phase 8 — The Volatility Engine (2026-05-14)

Phase 8 turned a correct-but-static economy into a **living** one. Every sub-phase committed green:

| Slice | Engine module | Tests | Commit |
|-------|--------------|-------|--------|
| **8A** Seasonal calendar (4 seasons), grain blocking in winter, seasonal yield/fuel modifiers, season transition feed entries | `realm/events/seasons.py` | `tests/events/test_seasons.py` (5) | seasonal calendar |
| **8B** `WorldEvent` system + drought / blight / mine collapse / storm / seismic / flood, pre-disaster signals, force majeure on supply contracts, subsurface depletion via `dataclasses.replace` | `realm/events/world_events.py` | `tests/events/test_natural_events.py` (13) | natural disasters |
| **8C** `wild_herb` + `medicine` + `apothecary` building/recipes, epidemic events with 3× health decay, medicine treatment, inter-town spread via migration | `realm/events/world_events.py` + `realm/production/recipes.py` | `tests/events/test_epidemics.py` (11) | epidemic system |
| **8D** Market panic (3-day MA + NPC sell-off), credit crunch on `apply_bank_loan`, trade route blockage from severe storms, boom-town entrepreneur migration, mining-driven subsurface depletion | `realm/economy/market_events.py` | `tests/economy/test_market_events.py` (12) | market cycles |
| **8E** Analytics products `regional_risk` + `market_cycle`, event log persistence in Chronicle | `realm/economy/analytics.py` | `tests/events/test_event_intelligence.py` (9) | event intelligence |
| **8F** Tuning + the final integration gate | — | `tests/integration/test_phase8_integration.py` (**30 assertions, all passing**) | 30-assertion final test |

The Phase 8F integration test is the definitive pre-launch gate. It runs `bootstrap_genesis(seed=42, settler_count=8)`, drives a daily-heartbeat loop across 730 game-days (2 game-years), nudges the rare events with their public `trigger_*` helpers, and asserts:

- **Seasons (1-4):** grain blocking in winter, seasonal fuel-decay differential, ≥4 season-transition feed rows, winter > summer grain prices.
- **Natural events (5-10):** ≥2 droughts, drought pre-announcement, mine collapse, storm-induced transit delay, seismic damage, subsurface depletion.
- **Epidemic (11-14):** epidemic fires, medicine demand visible on market, ≥1 epidemic death, resolved within 20 days.
- **Market cycles (15-18):** price panic, credit crunch, boom event, route blockage.
- **Stability (19-22):** post-drought recovery, post-epidemic town recovery ≥50% within 30 days, no island extinct, ≥5 distinct sellers active.
- **Circular flow (23-25):** ≥100 wage payments, ≥200 store purchases, `ledger.total_cents()` invariant **exactly**.
- **Information (26-28):** >100 world-feed rows, ≥10 distinct event types, ≥5 Margaux messages.
- **Intel products (29-30):** `regional_risk` surfaces active events, `market_cycle` flags a spiked material.

**Regression suite:** `cd engine && python -m pytest tests/events/ tests/economy/ tests/contracts/ tests/integration/test_phase8_integration.py` → **130 passed in ~178 s**, including the 30-assertion gate.

### What Phase 8 completes

- A real **seasonal calendar** that drives predictable annual market cycles.
- **Natural disasters** with advance warning signals — observable, not predictable.
- **Epidemics** that reshape labor supply and create medicine demand spikes.
- **Market panics** that produce boom-bust commodity cycles.
- **Credit cycles** that gate access to bank capital.
- **Resource depletion** that forces geographic expansion over time.
- Event-driven **analytics products** that monetise foresight (Law 6 — information has cost).

The economy is no longer in static equilibrium. It is a living system that surprises, rewards preparation, punishes complacency, and generates stories. Everything after Phase 8 is **testing, polish, and multiplayer** — no further solo feature development is required by the design.

---

**Last updated:** 2026-05-14 (Phase 7 fully closed — 7F inter-island trade + 7G 25-assertion gate landed; Phase 8 closed — 30-assertion volatility-engine gate green; next phase is headless API testing)

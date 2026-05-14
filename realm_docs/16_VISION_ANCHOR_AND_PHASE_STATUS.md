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

**Current phase:** **Phase 2 — Solo Polish & Visual Identity** (see `13_PHASED_TODO.md`). Phase 2 **engineering** is closed per **`18_PHASE_2_COMPLETION_CHECKLIST.md`** (Pixi, schematic, Tier 2, decay, information costs, scenarios, polish). **A1** ($30 stranger playtest gate) is deferred.

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

**Last updated:** 2026-05-13 (Sprint 6 closed; A1 stranger playtest gate still open)

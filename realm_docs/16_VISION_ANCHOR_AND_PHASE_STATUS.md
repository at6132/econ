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

Phase 1 **engineering checklist** is closed (`17_PHASE_1_COMPLETION_CHECKLIST.md`).

### Phase 1 checklist — honest snapshot (rolling)

This is a **status snapshot**, not a promise every box is finished to final quality.

**2026-05-08 — Phase transition:** Phase 1 **B–E** ✅ per `17_PHASE_1_COMPLETION_CHECKLIST.md`. **2026-05-10:** Phase 2 **engineering** ✅ per `18_PHASE_2_COMPLETION_CHECKLIST.md`. Stranger **$30** gate remains **A1** (deferred).

**Engine core (Phase 1 intent)**

| Item | Status |
|------|--------|
| Tick-based deterministic loop | **Yes** — `advance_tick`; RNG via `(tick, purpose)` |
| World generation | **Yes** — Frontier bootstrap; grid larger than doc’s “30–50 plots” example (stress) |
| Plots (Primitive 1) | **Yes** — terrain, ownership, survey reveals subsurface |
| Materials (Primitive 2) | **Yes** — starter set + spoilage transform; party storage cap + building bonus |
| Capital (Primitive 5) | **Yes** — accounts, transfers, conservation enforced |
| Production (Primitive 6) | **Yes** — recipes, runs, ticks; building labor BPS on plot |
| Movement (Primitive 4) | **Yes** — shipping / transit by tick distance; deliveries respect storage cap |
| Order books (Primitive 7b) | **Yes** — asks + bids, escrow, crossing; FIFO at price level by `order_id` |
| P2P trade (Primitive 7a) | **Yes** — atomic trade + optional idempotency + stable error codes |
| Contracts (Primitive 8) | **Phase 1 slice** — supply FSM + stub memo / hire |
| Reputation | **Phase 1 slice** — counters + supply / memo hooks |
| Code / Lua services (Primitive 9) | **Explicitly later** — Phase 4+ per roadmap |

**AI agents**

| Item | Status |
|------|--------|
| Tier 1 behavioral NPC loops | **Yes** — six loops (see `agents_tier1.py` docstring) |
| Tier 2 / 3 | **Tier 2** shipped (`agents_tier2.py`, `test_agents_tier2.py`); Tier 3 not Phase 2 |

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

**Last updated:** 2026-05-08 (code checklist aligned with doc 17; A1 playtest gate still open)

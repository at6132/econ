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

**Current phase:** **Phase 1 — Solo Engine Prototype (ugly-but-functional).**

We are **not** in Phase 0 as a coding freeze (spec exists and code is underway). We are **not** in Phase 2+ (no Pixi map requirement met; no commercial solo launch).

### Phase 1 checklist — honest snapshot (rolling)

This is a **status snapshot**, not a promise every box is finished to final quality.

**Engine core (Phase 1 intent)**

| Item | Status |
|------|--------|
| Tick-based deterministic loop | **In progress** — manual tick, deterministic RNG patterns |
| World generation | **Partial** — Frontier bootstrap; plot grid + coherent biomes; larger than doc’s “30–50 plots” example |
| Plots (Primitive 1) | **Partial** — terrain, ownership, survey reveals subsurface |
| Materials (Primitive 2) | **Partial** — starter set; conservation paths tested on key flows |
| Capital (Primitive 5) | **Partial** — accounts, transfers, conservation enforced |
| Production (Primitive 6) | **Partial** — recipes, runs, ticks |
| Movement (Primitive 4) | **Partial** — shipping / transit by tick distance |
| Order books (Primitive 7b) | **Partial** — asks + buy; not full matching engine |
| P2P trade (Primitive 7a) | **Stub / partial** |
| Contracts (Primitive 8) | **Stub** — not full primitive |
| Reputation | **Stub / partial** — counters exist |
| Code / Lua services (Primitive 9) | **Explicitly later** — Phase 4+ per roadmap |

**AI agents**

| Item | Status |
|------|--------|
| Tier 1 behavioral NPC loops | **Partial** — several scripted parties / market stubs |
| Tier 2 / 3 | **Not Phase 1** |

**Frontend**

| Item | Status |
|------|--------|
| Next.js shell | **Yes** |
| Map | **Yes** — data still plot lattice; **organic SVG mesh** is presentation |
| Market / logistics / contracts / log UI | **Partial** — Bloomberg-style panels, not all Phase 1 menu items as separate pages |
| Schematic plot view | **No** (Phase 2 territory per doc 13) |

**Persistence**

| Item | Status |
|------|--------|
| SQLite save / load | **Present** in stack |

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

**Last updated:** 2026-05-10 (doc 16 introduced)

# 18 — Phase 2 completion checklist (full depth)

> **Source of truth for scope:** `13_PHASED_TODO.md` — Phase 2 *Solo Polish & Visual Identity*.  
> This doc mirrors `17_PHASE_1_COMPLETION_CHECKLIST.md`: **build + test + UI** rows, **full-depth** (no “checkbox only” stubs).

### Legend

| Symbol | Meaning |
|--------|--------|
| ✅ | Implemented to a **usable** Phase 2 bar |
| 🟡 | **Partial** — in progress, shallow UX, or missing tests/docs |
| ❌ | **Not started** |
| ➖ | N/A |

### Verification commands

```bash
cd engine && python -m pytest tests/ -q
cd web && npx tsc --noEmit && npm run build
```

---

## A. Phase 2 exit criteria (doc 13)

| # | Gate | Status | Notes |
|---|------|--------|-------|
| A1 | **5 strangers**, **5+ h** each (multi-session); **≥3/5** “I’d buy for **$30** today” | ➖ | Human gate — schedule when B–H are largely ✅ |
| A2 | Visual + engine + content rows below at ✅ or justified 🟡 | 🟡 | Track honestly as work lands |

---

## B. Visuals & client (`web/app/`)

| # | Feature (doc 13) | Status | Notes / files |
|---|------------------|--------|----------------|
| B1 | **Pixi.js** map — terrain, plot boundaries, ownership | 🟡 | **Target:** `@pixi/react` or `pixi.js` layer; toggle vs SVG mesh; same world DTO |
| B2 | **Schematic plot view** — drag-drop production flow | ❌ | Distinct from map; Phase 2 centerpiece |
| B3 | **Real charting** (Recharts) — polished market UX | 🟡 | Symbol watchlist + depth exists; extend styling, tooltips, empty states |
| B4 | Polished **panels**, **command palette**, **keyboard shortcuts** | 🟡 | Settings + toasts scaffold; palette/shortcuts TBD |
| B5 | **Notification** system (in-app toaster) | 🟡 | Toast provider + hooks; wire key actions |
| B6 | **Settings** — speed, pause, save management, scenario | 🟡 | Local + engine scenario on reset |

---

## C. Engine extensions (`engine/realm/`)

| # | Feature | Status | Tests | Notes |
|---|---------|--------|-------|-------|
| C1 | **Tier 2** optimizing agents — ≥4 archetypes | 🟡 | `test_agents_tier2` (add) | Market-making / inventory / spread — not Tier 1 duplicates |
| C2 | **~25 materials** | 🟡 | inventory/production | Expand `materials.py` + recipes with conservation tests |
| C3 | **~15 recipe templates** | 🟡 | `test_production` | Plot/terrain gates optional; chain realism |
| C4 | **Loan / equity / service-subscription** contract **stubs** | ❌ | `test_contracts_*` | FSM + API + UI stubs per primitive 8 |
| C5 | **Surveying** as full mechanic (cost, reveal, information market) | 🟡 | `test_actions` | Phase 1 has survey cost; Phase 2: tradable survey intel / depth |
| C6 | **Decay** (Law 5) — buildings / upkeep | 🟡 | `test_decay` | Condition BPS, maintenance spend, storage/labor falloff |
| C7 | **Information cost** (Law 6) — e.g. paid market history | 🟡 | `test_intel` | Free window vs subscription/expiry; conservation on fee |

---

## D. HTTP API (`engine/realm/api.py`)

| # | Route / capability | Status |
|---|-------------------|--------|
| D1 | `POST /plots/{id}/maintain` — pay to restore **building condition** | 🟡 |
| D2 | `POST /market/intel` — purchase extended **market_history** visibility | 🟡 |
| D3 | `POST /dev/reset?scenario=` — **Frontier / Bootstrapper / Speculator / Cartel** | 🟡 |
| D4 | World DTO flags: `scenario_id`, `market_intel_active`, truncated history policy | 🟡 |

---

## E. Content — scenarios (doc 05 / 13)

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| E1 | **Frontier** (default) | ✅ | Existing bootstrap |
| E2 | **The Bootstrapper** | 🟡 | Smaller grid, tighter cash — tune in `world.py` |
| E3 | **The Speculator** | 🟡 | More starting cash, same engine |
| E4 | **The Cartel** | 🟡 | Placeholder: distinct NPC funding / prices — deepen later |
| E5 | Scenario **selection UI** | 🟡 | Settings + dev reset |

---

## F. Persistence (`state_io.py`)

| # | Item | Status |
|---|------|--------|
| F1 | Snapshot **version** bump or additive fields (`scenario_id`, `market_intel_expires_tick`, building `instance_id` / `condition_bps`, `next_building_instance_seq`) | 🟡 |
| F2 | Roundtrip tests for new fields | 🟡 |

---

## G. Definition of done (Phase 2 code — strict)

- [ ] **Law 5:** decay + maintenance paths have **pytest** + conservation on fees.
- [ ] **Law 6:** intel purchase moves **cash** through ledger; free tier documented in API.
- [ ] **Tier 2** distinct from Tier 1 schedules; documented in module docstring.
- [ ] **Pixi** map usable as **primary** or **toggle** view without breaking actions.
- [ ] **Schematic** plot MVP (even if ugly): edit graph → validates against recipes.
- [ ] `pytest` + `tsc` + `next build` green.

---

## H. Related docs

- `13_PHASED_TODO.md` — phase definition + **$30** test gate  
- `17_PHASE_1_COMPLETION_CHECKLIST.md` — closed Phase 1 record  
- `16_VISION_ANCHOR_AND_PHASE_STATUS.md` — rolling status  
- `06_AI_AGENT_DESIGN.md` — Tier 2 behavior expectations  

**Last updated:** 2026-05-08 — Phase 2 opened; checklist seeded from doc 13.

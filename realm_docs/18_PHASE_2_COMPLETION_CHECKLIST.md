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
| A2 | Visual + engine + content rows below at ✅ or justified 🟡 | 🟡 | B-renderer + schematic + stubs landed; content depth still 🟡 |

---

## B. Visuals & client (`web/app/`)

| # | Feature (doc 13) | Status | Notes / files |
|---|------------------|--------|----------------|
| B1 | **Pixi.js** map — terrain, plot boundaries, ownership | ✅ | `pixi.js` v8 canvas; **SVG / GL** toolbar toggle; same `OrganicMesh` / world DTO (`RealmMapMeshPixi.tsx`) |
| B2 | **Schematic plot view** — drag-drop production flow | ✅ | `PlotSchematicPanel.tsx` + per-plot `localStorage`; **engine** `POST /plots/{id}/schematic/validate` (`realm/schematic.py`, tests) |
| B3 | **Real charting** (Recharts) — polished market UX | 🟡 | Grid, tooltip labels, empty states; deeper watchlist/depth polish optional |
| B4 | Polished **panels**, **command palette**, **keyboard shortcuts** | 🟡 | Cmd/Ctrl+K palette + “Go to…”; tab shortcuts beyond palette still light |
| B5 | **Notification** system (in-app toaster) | 🟡 | `realmToast.tsx` + success toasts on many actions; not exhaustive |
| B6 | **Settings** — speed, pause, save management, scenario | 🟡 | HUD + Chronicle dev controls; no dedicated settings screen |

---

## C. Engine extensions (`engine/realm/`)

| # | Feature | Status | Tests | Notes |
|---|---------|--------|-------|-------|
| C1 | **Tier 2** optimizing agents — ≥4 archetypes | 🟡 | `test_agents_tier2` (add) | Market-making / inventory / spread — not Tier 1 duplicates |
| C2 | **~25 materials** | 🟡 | inventory/production | Expand `materials.py` + recipes with conservation tests |
| C3 | **~15 recipe templates** | 🟡 | `test_production` | Plot/terrain gates optional; chain realism |
| C4 | **Loan / equity / service-subscription** contract **stubs** | ✅ | `test_contract_stubs.py` | `contract_stubs.py` + tick FSM + `api.py` routes + dev UI on `page.tsx` |
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
| D5 | `POST /plots/{id}/schematic/validate` — authoritative recipe-chain check (`realm/schematic.py`, `test_schematic.py`) | ✅ |

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

- [ ] **Law 5:** decay + maintenance paths have **pytest** + conservation on fees. *(tests exist — re-verify on each change.)*
- [ ] **Law 6:** intel purchase moves **cash** through ledger; free tier documented in API.
- [ ] **Tier 2** distinct from Tier 1 schedules; documented in module docstring.
- [x] **Pixi** map usable as **primary** or **toggle** view without breaking actions.
- [x] **Schematic** plot MVP: edit chain → validates against **engine** recipes + party inventory (`/schematic/validate`).
- [x] `pytest` + `tsc` + `next build` green *(run before release; last full pytest: 82 passed)*.

---

## H. Related docs

- `13_PHASED_TODO.md` — phase definition + **$30** test gate  
- `17_PHASE_1_COMPLETION_CHECKLIST.md` — closed Phase 1 record  
- `16_VISION_ANCHOR_AND_PHASE_STATUS.md` — rolling status  
- `06_AI_AGENT_DESIGN.md` — Tier 2 behavior expectations  

**Last updated:** 2026-05-10 — Synced with repo: Pixi toggle, schematic + API, palette/toasts, C4 stubs tests; G partially closed.

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
| A2 | Visual + engine + content rows **B–H** at ✅ | ✅ | Engineering complete; **A1** ($30 stranger gate) deferred by project choice |

---

## B. Visuals & client (`web/app/`)

| # | Feature (doc 13) | Status | Notes / files |
|---|------------------|--------|----------------|
| B1 | **Pixi.js** map — terrain, plot boundaries, ownership | ✅ | `pixi.js` v8 canvas; **SVG / GL** toolbar toggle; same `OrganicMesh` / world DTO (`RealmMapMeshPixi.tsx`) |
| B2 | **Schematic plot view** — drag-drop production flow | ✅ | `PlotSchematicPanel.tsx` + per-plot `localStorage`; **engine** `POST /plots/{id}/schematic/validate` (`realm/schematic.py`, tests) |
| B3 | **Real charting** (Recharts) — polished market UX | ✅ | `MarketHistoryChart.tsx`: axis labels, Bazaar symbol sync, empty copy; grid + tooltips |
| B4 | Polished **panels**, **command palette**, **keyboard shortcuts** | ✅ | Cmd/Ctrl+K (`FrontierCommandPalette.tsx`); tab strip + palette “Go to…”; Phase 2 bar met |
| B5 | **Notification** system (in-app toaster) | ✅ | `realmToast.tsx` — success/error on major actions (orders, produce, ship, contracts, decay, intel, maintain) |
| B6 | **Settings** — speed, pause, save management, scenario | ✅ | `FrontierSettingsModal.tsx` (pause/speed, scenario + dev reset behind internal flag); palette entry |

---

## C. Engine extensions (`engine/realm/`)

| # | Feature | Status | Tests | Notes |
|---|---------|--------|-------|-------|
| C1 | **Tier 2** optimizing agents — ≥4 archetypes | ✅ | `test_agents_tier2.py` | Five archetypes in `agents_tier2.py`; `tick_tier2_agents` in `advance_tick`; module docstring ↔ doc 06 |
| C2 | **~25 materials** | ✅ | `test_catalog_depth.py` | **27** entries in `materials.py` `MATERIALS` |
| C3 | **~15 recipe templates** | ✅ | `test_production.py`, `test_catalog_depth.py` | **20** recipes in `recipes.py` `RECIPES` |
| C4 | **Loan / equity / service-subscription** contract **stubs** | ✅ | `test_contract_stubs.py` | `contract_stubs.py` + tick FSM + `api.py` routes + dev UI on `page.tsx` |
| C5 | **Surveying** as full mechanic (cost, reveal, information market) | ✅ | `test_actions`, `test_api_routes` | `survey_plot` → system reserve; HTTP `/plots/{id}/survey`; terrain + `recipe_ids` on response; deeper “tradable survey intel” still optional |
| C6 | **Decay** (Law 5) — buildings / upkeep | ✅ | `test_decay` | `tick_building_decay`; `maintain_building` fee `max(1_000, cost//5)` + ledger conservation; labor bonus gate via condition |
| C7 | **Information cost** (Law 6) — e.g. paid market history | ✅ | `test_intel`, `test_api_routes` | `purchase_market_intel`; `FREE_MARKET_HISTORY_TICKS` truncation vs paid expiry; fee → system reserve; HTTP `/market/intel` |

---

## D. HTTP API (`engine/realm/api.py`)

| # | Route / capability | Status | Notes |
|---|-------------------|--------|-------|
| D1 | `POST /plots/{id}/maintain` — pay to restore **building condition** | ✅ | |
| D2 | `POST /market/intel` — purchase extended **market_history** visibility | ✅ | |
| D3 | `POST /dev/reset?scenario=` — **Frontier / Bootstrapper / Speculator / Cartel** | ✅ | `api.py` + `bootstrap_by_scenario`; `test_dev_reset_scenarios.py` |
| D4 | World DTO flags: `scenario_id`, `market_intel_active`, truncated history policy | ✅ | `world_public_dict`: `scenario_id`, `market_intel_expires_tick`, `market_intel_active`, truncated `market_history` vs `FREE_MARKET_HISTORY_TICKS` |
| D5 | `POST /plots/{id}/schematic/validate` — authoritative recipe-chain check (`realm/schematic.py`, `test_schematic.py`) | ✅ | |

---

## E. Content — scenarios (doc 05 / 13)

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| E1 | **Frontier** (default) | ✅ | Existing bootstrap |
| E2 | **The Bootstrapper** | ✅ | `bootstrap_by_scenario`: 32×24 grid, **$5,000** starting cash (`starting_cash_cents=500_000`) |
| E3 | **The Speculator** | ✅ | 40×30 grid, **$20,000** start (`2_000_000` cents); tests in `test_dev_reset_scenarios.py` |
| E4 | **The Cartel** | ✅ | Same bootstrap as Frontier + `_seed_cartel_grain_overlay` (distinct grain-side pressure); engine-identical rules |
| E5 | Scenario **selection UI** | ✅ | `FrontierSettingsModal` scenario dropdown + `POST /dev/reset?scenario=` |

---

## F. Persistence (`state_io.py`)

| # | Item | Status | Notes |
|---|------|--------|-------|
| F1 | Snapshot **version** bump or additive fields (`scenario_id`, `market_intel_expires_tick`, building `instance_id` / `condition_bps`, `next_building_instance_seq`) | ✅ | `state_io.py` **SNAPSHOT_VERSION 2**; full party inventory dump/load |
| F2 | Roundtrip tests for new fields | ✅ | `test_state_io_roundtrip.py` |

---

## G. Definition of done (Phase 2 code — strict)

- [x] **Law 5:** decay + maintenance paths have **pytest** + conservation on fees (`test_decay`, `test_api_routes` HTTP maintain).
- [x] **Law 6:** intel purchase moves **cash** through ledger (`test_intel`, `test_api_routes`); free tier: last `FREE_MARKET_HISTORY_TICKS` snapshots unless `market_intel_expires_tick` ≥ tick (`intel.py`, `world_public_dict`).
- [x] **Tier 2** distinct from Tier 1 schedules; documented in module docstring (`agents_tier2.py`).
- [x] **Pixi** map usable as **primary** or **toggle** view without breaking actions.
- [x] **Schematic** plot MVP: edit chain → validates against **engine** recipes + party inventory (`/schematic/validate`).
- [x] `pytest` + `tsc` + `next build` green *(run before release; last verified: engine **117 passed**, web `tsc` + `next build` OK, 2026-05-10)*.

---

## H. Related docs

- `13_PHASED_TODO.md` — phase definition + **$30** test gate  
- `17_PHASE_1_COMPLETION_CHECKLIST.md` — closed Phase 1 record  
- `16_VISION_ANCHOR_AND_PHASE_STATUS.md` — rolling status  
- `06_AI_AGENT_DESIGN.md` — Tier 2 behavior expectations  

**Last updated:** 2026-05-10 — Phase 2 **engineering checklist closed** (no 🟡 on in-scope rows; **A1** remains ➖ human gate, deferred). Persistence v2, scenarios, Tier 2, catalog depth tests, Settings modal, chart polish; engine pytest **117**, web build green.

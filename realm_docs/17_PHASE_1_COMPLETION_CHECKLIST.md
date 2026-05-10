# 17 — Phase 1 completion checklist (full depth)

> **Source of truth for scope:** `13_PHASED_TODO.md` — Phase 1 *Solo Engine Prototype (Ugly But Functional)*.  
> **This doc** turns that phase into a **build + test + UI** checklist you can work to “done,” including **full-depth** items (not just stubs).

### Legend

| Symbol | Meaning |
|--------|--------|
| ✅ | Implemented to a **usable** level for Phase 1 |
| 🟡 | **Partial** — exists but shallow, missing UI/API/tests, or diverges from spec wording |
| ❌ | **Missing** or explicitly out of scope for Phase 1 |
| ➖ | N/A (e.g. “no Tier 2”) |

### Verification commands (run before calling Phase 1 “green”)

```bash
# Engine
cd engine && python -m pytest tests/ -q

# Web
cd web && npx tsc --noEmit && npm run build
```

Optional: run the FastAPI app and click through `web` against a live engine (`REALM_ENGINE_ORIGIN` if not on port 8000).

---

## A. Phase 1 exit criteria (doc 13)

| # | Gate | Status | Notes |
|---|------|--------|-------|
| A1 | **Stranger playtest:** 3–5 people, ~1 h each; **3/5** would play another hour | ❌ | Process / evidence, not a code checkbox |
| A2 | All **B–E** rows below at ✅ for “Phase 1 minimum,” or 🟡 only where explicitly deferred | 🟡 | Use this doc to drive to ✅ |
| A3 | **Conservation:** money + matter paths touched by new code have **pytest** coverage | 🟡 | Expand where 🟡 features deepen |

---

## B. Engine core (Python: `engine/realm/`)

| # | Feature (Phase 1 doc) | Engine | Tests | “Full depth” stretch | Status |
|---|------------------------|--------|-------|----------------------|--------|
| B1 | Tick loop, deterministic time | `tick.py` → `advance_tick` | `test_phase1_extended`, production tests | RNG only via `make_rng(tick, purpose)`; no wall-clock in sim | ✅ |
| B2 | World generation (doc: 30–50 plots) | `world.py` `generate_plots` + `biome_noise.py` | `test_world.py`, `test_biome_noise.py` | **Either** shrink default to spec **or** update doc to match intentional scale | 🟡 |
| B3 | Plots: terrain, **hidden** subsurface, ownership | `world.py`, `actions.py` claim/survey | `test_actions.py` | Subsurface only after survey in public dict; **survey cost** if spec requires | 🟡 |
| B4 | Materials ~10, properties | `materials.py` (11 defs) | `test_inventory.py` | Per-material behavior (decay, storage) — **Law 5** often Phase 2 | ✅ / 🟡 |
| B5 | Capital: accounts, atomic transfers, **conservation** | `ledger.py` | `test_ledger.py`, `test_world.py` | Invariant tests: total cents constant except designed mint/burn | ✅ |
| B6 | Production: ~5 recipes | `recipes.py` (5), `production.py` | `test_production.py` | **Labor as real input** to runs; building modifiers | 🟡 |
| B7 | Movement: transport, time, cost | `movement.py` | `test_phase1_extended` shipment | Fee formula vs distance documented + tested | 🟡 |
| B8 | Order book (7b) | `markets.py` — **asks only**, `market_buy` walks book | `test_phase1_extended` | **Bids**, partial fills policy, cancel edge cases, **matching** rules documented | 🟡 |
| B9 | P2P trade (7a) | `markets.py` `p2p_trade` | `test_phase1_extended` | UI + idempotency + failure reasons in API | 🟡 |
| B10 | Basic contracts: **supply + employment** | `social.py` **stub** dicts; `actions.py` hire stub | `test_phase1_extended` | Typed contract state machine; **breach** path; performance clauses | 🟡 |
| B11 | Reputation (doc calls it “placeholder”) | `world.reputation` + honor stub | `test_phase1_extended` | Separate **breach** flow; reputation affects something (even stub discount) | 🟡 |

---

## C. HTTP API (`engine/realm/api.py`)

Wire each action the UI needs; return `{ ok, ... } | { ok: false, reason }`.

| # | Route / capability | Implemented | Frontend wired | Notes |
|---|-------------------|-------------|------------------|-------|
| C1 | `GET /health` | ✅ | ➖ | |
| C2 | `GET /world` | ✅ | ✅ | |
| C3 | `POST /tick` | ✅ | ✅ | |
| C4 | `POST /plots/{id}/claim` | ✅ | ✅ | |
| C5 | `POST /plots/{id}/survey` | ✅ | ✅ | |
| C6 | `POST /plots/{id}/produce` | ✅ | ✅ | |
| C7 | `POST /plots/{id}/build` | ✅ | ✅ | |
| C8 | `GET /hire/catalog` | ✅ | ✅ (via world DTO) | |
| C9 | `POST /hire` | ✅ | ✅ | |
| C10 | `POST /ship` | ✅ | ✅ | |
| C11 | `POST /market/sell` | ✅ | ✅ | |
| C12 | `POST /market/buy` | ✅ | ✅ | |
| C13 | `POST /market/cancel` | ✅ | ❌ | **Add UI** to cancel player asks |
| C14 | `POST /trade/p2p` | ✅ | ❌ | **Add UI** for player↔NPC or player↔player P2P |
| C15 | `POST /contracts/propose` | ✅ | ✅ | Stub only |
| C16 | `POST /contracts/{id}/honor` | ✅ | ✅ | Stub only |
| C17 | `POST /persistence/save` | ✅ | ✅ | |
| C18 | `POST /persistence/load` | ✅ | ✅ | |
| C19 | `POST /dev/reset` | ✅ | ❌ | Optional dev-only UI or document for QA |

**Next.js:** `web` calls `/api/engine/*` → rewrite to engine (`next.config.mjs`, `REALM_ENGINE_ORIGIN`).

---

## D. Frontend (`web/app/` — primarily `page.tsx` + map components)

Phase 1 doc lists **dedicated views**. Today many are **tabs in one command panel** — that’s fine if every **action** is reachable and readable.

| # | Phase 1 UI item | Present | Quality / gap |
|---|-----------------|---------|----------------|
| D1 | Next.js app shell | ✅ | |
| D2 | World map (no Pixi required) | ✅ | SVG organic mesh; OK for Phase 1 |
| D3 | Plot detail — tables + buttons | ✅ | Under **Territory & works**; ensure empty-state copy |
| D4 | Market — **table** order book + chart | 🟡 | Book + Recharts history; **no bid book**; **no cancel** in UI |
| D5 | Inventory — **table** | 🟡 | Section exists; ensure **all parties** or clear “player only” + doc |
| D6 | Build menu (costs) | ✅ | From `building_catalog` |
| D7 | Hire menu (wages / signing) | 🟡 | Stub hire; not full employment economy |
| D8 | Action log | ✅ | `event_log` |
| D9 | Logistics (in transit + ship) | ✅ | **Caravans** tab |
| D10 | Contracts UI | 🟡 | Stubs only |
| D11 | P2P trade UI | ❌ | Wire `POST /trade/p2p` |
| D12 | Market cancel UI | ❌ | Wire `POST /market/cancel` |

---

## E. Tier 1 AI agents (`engine/realm/agents_tier1.py`)

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| E1 | ~6 behavioral archetypes | ✅ | Grain consumer, lumber buyer, timber relister, coal, clay, electricity buyer |
| E2 | No Tier 2 / 3 | ➖ | |

**Full depth:** document each agent’s **trigger**, **budget**, and **failure** (why it skips a tick); add tests that a long run doesn’t violate conservation.

---

## F. Persistence (`engine/realm/persistence.py`, `state_io.py`)

| # | Item | Status | Tests |
|---|------|--------|-------|
| F1 | SQLite save | ✅ | `test_phase1_extended.test_sqlite_roundtrip` |
| F2 | SQLite load | ✅ | same |
| F3 | Forward-compat / migration note | ❌ | Optional Phase 1 doc string in save format |

---

## G. Test file inventory (`engine/tests/`)

| File | Covers (high level) | Gaps to add for “full” Phase 1 |
|------|---------------------|--------------------------------|
| `test_world.py` | bootstrap money, gen deterministic, public dict subsurface | Default plot count vs doc 13 |
| `test_biome_noise.py` | terrain deterministic | More threshold / regression vectors |
| `test_ledger.py` | ledger conservation | Concurrent-style transfers if ever added |
| `test_inventory.py` | matter add/remove | Cross-party transfers, edge qty |
| `test_actions.py` | claim, survey | Survey cost if added |
| `test_production.py` | recipes, reject duplicate run | Labor + building modifiers |
| `test_production.py` | — | **market cancel** unit tests |
| `test_phase1_extended.py` | JSON/SQLite roundtrip, ship, p2p, market buy, build/hire, contracts stub, market history | **Bids**, **full contract** flows, **API-level** tests (optional `TestClient`) |
| `test_rng.py` | RNG | — |

**Stretch:** `tests/test_api_http.py` using FastAPI `TestClient` for every route in section C.

---

## H. “Full not shallow” — recommended completion order

1. **Market depth:** `market/cancel` UI + tests; then **limit bids** + symmetric matching (biggest Phase 1 gap vs wording “order books”).
2. **P2P UI** + one pytest for API JSON shape.
3. **Contracts:** replace stub with minimal **supply** contract (deliver qty by tick N, breach marks reputation).
4. **Employment:** hiring affects **production capacity** or wage line item on runs (even one recipe).
5. **Playtest gate A1** — schedule strangers; capture notes.

---

## I. Definition of done (Phase 1 code — suggested strict version)

- [ ] Every **C** row that is ✅ on the engine has either **UI** or an explicit **“engine-only / dev”** note.
- [ ] No 🟡 in **B8, B10, B11** without a tracked follow-up (or doc 13 amended).
- [ ] `pytest` green; `tsc` + `next build` green.
- [ ] **A1** playtest completed or consciously deferred with a dated note in `16_VISION_ANCHOR_AND_PHASE_STATUS.md`.

---

## J. Related docs

- `13_PHASED_TODO.md` — phase definition + test gate  
- `16_VISION_ANCHOR_AND_PHASE_STATUS.md` — vision + coarse status  
- `03_PRIMITIVES_SPEC.md` / `04_LAWS_OF_THE_UNIVERSE.md` — primitive + law checks when deepening features  

**Last updated:** 2026-05-10

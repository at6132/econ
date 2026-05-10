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
| A2 | All **B–E** rows below at ✅ for “Phase 1 minimum,” or 🟡 only where explicitly deferred | ✅ | **A1** (stranger playtest) remains the only human gate; B2 default grid > doc 13 minimum (intentional Frontier stress) |
| A3 | **Conservation:** money + matter paths touched by new code have **pytest** coverage | ✅ | Supply, production+labor split, movement fee, markets, 60-tick agent ledger smoke |

---

## B. Engine core (Python: `engine/realm/`)

| # | Feature (Phase 1 doc) | Engine | Tests | “Full depth” stretch | Status |
|---|------------------------|--------|-------|----------------------|--------|
| B1 | Tick loop, deterministic time | `tick.py` → `advance_tick` | `test_phase1_extended`, production tests | RNG only via `make_rng(tick, purpose)`; no wall-clock in sim | ✅ |
| B2 | World generation (doc: 30–50 plots) | `world.py` `generate_plots` + `biome_noise.py` | `test_world.py`, `test_biome_noise.py` | **Frontier default** grid **>** doc minimum (stress); small grids via bootstrap args / tests | ✅ |
| B3 | Plots: terrain, **hidden** subsurface, ownership | `world.py`, `actions.py` claim/survey | `test_actions.py` | Subsurface gated in public dict; **survey cost** `SURVEY_COST_CENTS` | ✅ |
| B4 | Materials ~10, properties | `materials.py` (12 defs incl. `spoiled_grain`) | `test_inventory.py`, `test_storage_spoilage.py` | Party-wide **storage unit cap** + `field_stockade` bonus; **grain → spoiled_grain** on a tick interval (1:1, Law 1) | ✅ |
| B5 | Capital: accounts, atomic transfers, **conservation** | `ledger.py` | `test_ledger.py`, `test_world.py` | Invariant tests: total cents constant except designed mint/burn | ✅ |
| B6 | Production: ~5 recipes | `recipes.py` (5), `production.py` | `test_production.py` | **Labor cash**: 40%→stub hires (even split), rest→reserve; **`tool_cache` / `watch_hut`** lower recipe labor **cash** on the producing plot (BPS) | ✅ |
| B7 | Movement: transport, time, cost | `movement.py` | `test_phase1_extended`, `test_movement` | Fee = `BASE + manhattan×PER_TILE` (module docstring) | ✅ |
| B9 | P2P trade (7a) | `markets.py` `p2p_trade` | `test_markets.py`, `test_phase1_extended`, `test_api_routes` | **Idempotency** (`idempotency_key` + fingerprint); **stable `code`** on outcomes; HTTP `detail: { reason, code }` | ✅ |
| B8 | Order book (7b) | `markets.py` — **asks + bids** (escrow on bids), cross incoming bid at **ask** price / incoming ask at **bid** limit; `market_buy`, `sell_into_bids` | `test_phase1_extended`, `test_markets`, `test_api_routes` | Iceberg, price–time priority within a level — deferred | ✅ |
| B10 | Basic contracts: **supply + employment** | `social.py` supply FSM; `actions.py` hire; `tick.py` breaches | `test_contracts_supply`, `test_phase1_extended`, `test_api_routes` | Rich performance clauses / full employment sim — later | ✅ |
| B11 | Reputation (doc calls it “placeholder”) | `world.reputation` + memo honor + supply fulfill/breach | `test_contracts_supply`, `test_phase1_extended` | Reputation-priced markets — later | ✅ |

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
| C13 | `POST /market/cancel` | ✅ | ✅ | Cancel **ask** — player rows in Bazaar |
| C14 | `POST /trade/p2p` | ✅ | ✅ | **P2P** on Bazaar tab; optional `idempotency_key` query param; 400 → `{ detail: { reason, code } }` |
| C15 | `POST /contracts/propose` | ✅ | ✅ | **Memo / generic** handshake only (`kind` ≠ `supply`; supply uses C23) |
| C16 | `POST /contracts/{id}/honor` | ✅ | ✅ | **Memo** honor — not used for supply (use C25 fulfill) |
| C17 | `POST /persistence/save` | ✅ | ✅ | |
| C18 | `POST /persistence/load` | ✅ | ✅ | Refetch + map pan re-init |
| C19 | `POST /dev/reset` | ✅ | ✅ | Chronicle → **Dev: reset world** (confirm) |
| C20 | `POST /market/bid` | ✅ | ✅ | Limit bid: `party`, `material`, `qty`, `max_price_per_unit_cents` |
| C21 | `POST /market/cancel_bid` | ✅ | ✅ | Refunds escrow |
| C22 | `POST /market/sell_fill` | ✅ | ✅ | Aggressive sell into bid book: `max_qty` |
| C23 | `POST /contracts/supply/propose` | ✅ | ✅ | `supplier`, `buyer`, `material`, `qty`, `total_price_cents`, `due_in_ticks` |
| C24 | `POST /contracts/supply/accept` | ✅ | ✅ | `buyer`, `contract_id` |
| C25 | `POST /contracts/supply/fulfill` | ✅ | ✅ | `supplier`, `contract_id` |

**Next.js:** `web` calls `/api/engine/*` → rewrite to engine (`next.config.mjs`, `REALM_ENGINE_ORIGIN`).

---

## D. Frontend (`web/app/` — primarily `page.tsx` + map components)

Phase 1 doc lists **dedicated views**. Today many are **tabs in one command panel** — that’s fine if every **action** is reachable and readable.

| # | Phase 1 UI item | Present | Quality / gap |
|---|-----------------|---------|----------------|
| D1 | Next.js app shell | ✅ | |
| D2 | World map (no Pixi required) | ✅ | SVG organic mesh; OK for Phase 1 |
| D3 | Plot detail — tables + buttons | ✅ | Under **Territory & works**; ensure empty-state copy |
| D4 | Market — **table** order book + chart | ✅ | Asks + bids tables, place/cancel bid, sell into bids; depth chart **ask + bid** series (dashed bids) |
| D5 | Inventory — **table** | ✅ | **Inventory (player)** |
| D6 | Build menu (costs) | ✅ | From `building_catalog` |
| D7 | Hire menu (wages / signing) | ✅ | Signing bonus + engine **per-run labor share** to hires (contracts tab) |
| D8 | Action log | ✅ | `event_log` |
| D9 | Logistics (in transit + ship) | ✅ | **Caravans** tab |
| D10 | Contracts UI | ✅ | Supply flow + table; memo honor (dev) |
| D11 | P2P trade UI | ✅ | Bazaar tab |
| D12 | Market cancel UI | ✅ | Player rows only — cancel **ask** or **bid** |

---

## E. Tier 1 AI agents (`engine/realm/agents_tier1.py`)

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| E1 | ~6 behavioral archetypes | ✅ | Grain consumer, lumber buyer, timber relister, coal, clay, electricity buyer |
| E2 | No Tier 2 / 3 | ➖ | |

**Full depth:** trigger/budget/failure per agent documented in `agents_tier1.py` module docstring; **ledger total** smoke: `test_phase1_extended.test_tier1_agent_ticks_conserve_total_cents`.

---

## F. Persistence (`engine/realm/persistence.py`, `state_io.py`)

| # | Item | Status | Tests |
|---|------|--------|-------|
| F1 | SQLite save | ✅ | `test_phase1_extended.test_sqlite_roundtrip` |
| F2 | SQLite load | ✅ | same |
| F3 | Forward-compat / migration note | ✅ | `state_io` module doc: version 1, additive fields via `.get` |
| F4 | Order book + P2P idempotency in snapshot | ✅ | `state_io`: `market_asks` + `market_bids` (+ bid `escrow_cents`); `p2p_idempotency`; `market_history` entries may omit `best_bids_cents` on old saves |

---

## G. Test file inventory (`engine/tests/`)

| File | Covers (high level) | Gaps to add for “full” Phase 1 |
|------|---------------------|--------------------------------|
| `test_world.py` | bootstrap money, gen deterministic, public dict subsurface | Default plot count vs doc 13 |
| `test_biome_noise.py` | terrain deterministic | More threshold / regression vectors |
| `test_ledger.py` | ledger conservation | Concurrent-style transfers if ever added |
| `test_inventory.py` | matter add/remove | Cross-party transfers, edge qty |
| `test_actions.py` | claim, survey | Survey cost covered in `actions.SURVEY_COST_CENTS` |
| `test_production.py` | recipes, reject duplicate run, **stub hire labor split**, **tool_cache labor BPS** | — |
| `test_markets.py` | Ask/bid cancel, crossing, `sell_into_bids`, escrow, **P2P idempotency** | — |
| `test_contracts_supply.py` | Supply propose/accept/fulfill, breach, wrong party | — |
| `test_movement.py` | Shipping fee = base + tile rate × Manhattan | Edge cases |
| `test_phase1_extended.py` | JSON/SQLite roundtrip, shipments, P2P, agents conservation, market history | — |
| `test_api_routes.py` | HTTP: markets, P2P (**structured errors**, idempotency), **supply flow**, cancel smoke | Full route matrix optional |
| `test_storage_spoilage.py` | Storage cap, stockade bonus, spoilage conservation | — |
| `test_rng.py` | RNG | — |

**Stretch:** extend `test_api_routes.py` with `TestClient` coverage for every route in section C.

---

## H. “Full not shallow” — recommended completion order

1. **Market depth:** ✅ limit bids, matching, persistence, API, UI, chart bid series; optional: richer depth / level-2 later.
2. **P2P:** ✅ UI + HTTP tests + **idempotency** + structured API errors.
3. **Contracts:** ✅ supply propose → accept → fulfill; deadline breach → supplier `breached`.
4. **Employment:** ✅ **40%** of recipe `labor_cents` paid to distinct `stub_hires` employees per batch (even split); remainder to reserve.
5. **Playtest gate A1** — schedule strangers; capture notes.

---

## I. Definition of done (Phase 1 code — suggested strict version)

- [x] Every **C** row that is ✅ on the engine has either **UI** or an explicit **“engine-only / dev”** note.
- [x] No 🟡 in **B10, B11** without a tracked follow-up (or doc 13 amended). (**B8** order book: ✅. **B10/B11**: ✅.)
- [x] Remaining **🟡** acceptable: **B2** grid size vs doc 13 example (intentional Frontier stress).
- [x] `pytest` green; `tsc` + `next build` green.
- [ ] **A1** playtest completed or consciously deferred with a dated note in `16_VISION_ANCHOR_AND_PHASE_STATUS.md`.

---

## J. Related docs

- `13_PHASED_TODO.md` — phase definition + test gate  
- `16_VISION_ANCHOR_AND_PHASE_STATUS.md` — vision + coarse status  
- `03_PRIMITIVES_SPEC.md` / `04_LAWS_OF_THE_UNIVERSE.md` — primitive + law checks when deepening features  

**Last updated:** 2026-05-08 (Phase 1 code gate green for A2; A1 recruiting next)

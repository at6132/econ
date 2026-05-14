# Realm engine — architecture

This document is the map. Read it first.

The engine is a deterministic, tick-based economic simulation written in Python.
It has one source of truth: `World`. Everything else (API, persistence,
serialization, UI) reads from `World` or asks an action to mutate it.

```
engine/
├── realm/                  ← the simulation (importable as `realm`)
│   ├── materials.py        ← MaterialId enum (only top-level domain file)
│   ├── inventory.py        ← back-compat shim → realm.core.inventory
│   ├── ledger.py           ← back-compat shim → realm.core.ledger
│   │
│   ├── core/               ← invariants & primitives. Imports from nothing else.
│   ├── world/              ← World state, plots, terrain, tick loop, serialization
│   ├── economy/            ← markets, pricing, market history, intel
│   ├── production/         ← recipes, buildings, production runs, decay/spoilage
│   ├── agents/             ← Tier-1 / Tier-2 / Tier-3 (LLM) agent loops
│   ├── genesis/            ← Genesis-scenario specific archetypes & scripts
│   ├── population/         ← labor pool, employment, towns, stores
│   ├── contracts/          ← supply/forward contracts, tenders, social DTOs
│   ├── actions/            ← player+agent action handlers (return ActionResult)
│   ├── infrastructure/     ← roads, energy, movement, route operators
│   ├── events/             ← event log + (future) world events / seasons
│   ├── code/               ← user Lua sandbox (Phase 4+)
│   └── api/                ← FastAPI app + routers (HTTP boundary)
│
├── tests/                  ← mirrors realm/ folder layout
│   ├── conftest.py         ← puts tests/ on sys.path for turnkey_fixtures
│   ├── turnkey_fixtures.py ← shared world fixtures
│   ├── core/  world/  economy/  production/  agents/  genesis/
│   ├── population/  contracts/  actions/  infrastructure/  events/
│   ├── code/  api/         ← per-domain test files
│   └── integration/        ← multi-domain / scenario tests
│
├── scripts/                ← one-off dev scripts (NOT shipped)
└── pyproject.toml
```

## The three laws (engine-enforced)

Every code change MUST satisfy these. Tests in `tests/core/` exist to catch
regressions; do not weaken or bypass them.

1. **Conservation** — `world.ledger.total_cents()` is invariant. Money only
   moves through `ledger.transfer(...)`. There is **no** direct mutation of
   account balances. Total cents at tick 0 == total cents at tick N.
2. **Matter atomicity** — Materials only move through
   `world.inventory.transfer_to(...)` or its internal `move(...)`. There is
   **no** direct mutation of `inventory.stock`. Materials are conserved
   per-recipe (input qty × multiplier == output qty × multiplier, modulo
   designed decay/spoilage which is itself accounted for).
3. **Determinism** — All randomness goes through `world.rng(tick, purpose)`
   (or `make_rng(seed, ...)` during bootstrap). No `random.random()`, no
   `Date.now()`, no `time.time()` in game logic. Same seed + same tick + same
   purpose → same bytes.

See `realm.core.conservation` for the snapshot/assert helpers used by tests.

## Dependency direction

Domains depend on lower layers, never upward.

```
core    ────────────────────────────────────────────────────────────►
world  ← depends on core
events ← depends on core
production    ← world + core
economy       ← world + core + production
infrastructure ← world + core + production
population    ← world + core + economy + production
contracts     ← world + core + economy + production
genesis       ← world + core + economy + production + population + contracts
agents        ← world + core + economy + production + population + contracts
actions       ← anything below (it is the player-facing entry point)
api           ← only domain that talks HTTP; imports `actions`
code          ← Lua sandbox; sits beside actions
```

Cycles are forbidden. If a primitive needs something from a higher layer,
inline-import it inside the function (not at module top) and consider whether
the dependency should be inverted.

## Modules at a glance

### `realm.core`

The smallest set of primitives, with **no other realm imports**.
- `ids.py` — `PartyId`, `PlotId`, `AccountId`, `MaterialId` (strong newtypes)
- `ledger.py` — `Ledger`, `MoneyResult`, `*_account()` helpers
- `inventory.py` — `Inventory`, `MatterResult`
- `rng.py` — `make_rng(seed, *parts)` deterministic factory
- `time_scale.py` — `TICKS_PER_GAME_DAY`, day/year helpers
- `sub_accounts.py` — sub-account ledger primitives (savings, escrow, etc.)
- `conservation.py` — `ConservationSnapshot` + `assert_*_conserved` helpers

`realm.ledger` and `realm.inventory` are kept as backward-compat shims so
older imports keep working, but new code should import from `realm.core`.

### `realm.world`

The world is the simulation state. **Read-only DTOs** (`world_public_dict`,
`world_compact_dict`, `world_summary_dict`) live in `serialization.py` so
`world.py` itself only owns mutable state and bootstrap.

- `world.py` — `World`, `Plot`, `ActiveProduction`, `InTransit`, `BusinessRecord`,
  `RoadSegment`, `SurveyReport`, `bootstrap_{frontier,genesis,by_scenario}`
- `subsurface.py` — `SubsurfaceRoll` + terrain-correlated worldgen roll
- `serialization.py` — JSON-shaped public/compact/summary dicts
- `terrain.py` — `Terrain` enum
- `biome_noise.py`, `geo.py`, `islands.py`, `geo_clustering.py`, `regions.py` — worldgen support
- `tick.py` — `advance_tick(world)` — the simulation loop

### `realm.actions`

Each `actions/*.py` file owns a small surface of state-mutating handlers
(claim plot, register business, hire worker, register route, …). All return
the `ActionResult` shape from `_shared.py`:

```python
ActionOk  = TypedDict("ActionOk",  {"ok": Literal[True],  ...})
ActionErr = TypedDict("ActionErr", {"ok": Literal[False], "reason": str})
ActionResult = ActionOk | ActionErr
```

Never raise for an expected rejection — return `{"ok": False, "reason": ...}`.

### `realm.api`

FastAPI lives here, split into per-domain routers:
- `app.py` — `FastAPI()`, CORS, `include_router` for everything below
- `routes_world.py` — `/health`, `/world`, `/tick`, `/llm`, `/code`, `/hire/catalog`
- `routes_actions.py` — player actions (POST endpoints)
- `routes_analytics.py` — analytics, market, bank, intel, alerts, tenders
- `routes_contracts.py` — supply/forward contracts, tenders
- `routes_dev.py` — `/dev/reset`, `/persistence/save`, `/persistence/load`
- `_state.py` — the shared mutable `WORLD` singleton + `_save_path` helper
- `serialization.py` — JSON helpers for save/load
- `persistence.py` — SQLite-backed save/load

The API has **no** game logic; it forwards to action handlers and returns the
result.

### Tests

`tests/` mirrors `realm/`. Anything that touches conservation lives next to
its domain (`tests/economy/test_markets.py`, `tests/production/test_decay.py`,
…). `tests/integration/` holds multi-domain scenario tests.

Tests run via:

```bash
cd engine
python -m pytest tests -n auto    # ~80s in parallel
```

`pytest-xdist` (`-n auto`) is recommended; the suite is ~5× faster in parallel.

## Where to add new code

| Change                                  | File / folder                          |
| --------------------------------------- | -------------------------------------- |
| New player-callable action              | `realm/actions/<domain>_actions.py`    |
| New HTTP endpoint                       | `realm/api/routes_<domain>.py`         |
| New recipe                              | `realm/production/recipes.py`          |
| New building catalog entry              | `realm/production/buildings.py`        |
| New worldgen roll                       | `realm/world/subsurface.py` (or new)   |
| New world-state field                   | `realm/world/world.py` (`@dataclass World`) |
| New public-dict field in `/world`       | `realm/world/serialization.py`         |
| New scenario archetype (genesis)        | `realm/genesis/archetypes.py`          |
| New deterministic-RNG site              | use `world.rng(tick, "purpose-tag")`   |
| New invariant test                      | `tests/core/test_conservation*.py`     |

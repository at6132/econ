# 21 — Realm Labs

Labs are **contained economic sandboxes** for strategy tests, market experiments, and social/agent dynamics — separate from the main Frontier campaign on the home screen.

## Catalog

- **Generated presets** — combinatorial lattice in `engine/realm/labs/preset_generator.py` (stable `gen_*` ids).
- **Featured presets** — hand-authored JSON in `engine/realm/labs/presets/featured/*.json` (narrative copy, `feat_*` ids). Featured entries override generated ids on collision.

List/count: `from realm.labs import catalog_stats, all_lab_presets`.

## Adding a featured lab

Create or extend a JSON file under `engine/realm/labs/presets/featured/`:

```json
{
  "id": "feat_my_lab",
  "title": "My Lab Title",
  "description": "One-line purpose.",
  "category": "Markets",
  "tags": ["featured", "grain"],
  "base": "frontier",
  "params": {
    "grid_width": 16,
    "grid_height": 12,
    "starting_cash_cents": 1000000,
    "scenario_id": "frontier"
  },
  "overlays": {},
  "featured": true
}
```

- `base`: `frontier` | `genesis` — which bootstrap path runs.
- `params`: passed to `bootstrap_frontier` / `bootstrap_genesis` (see those functions for valid keys).
- For cartel grain pressure use `"scenario_id": "cartel"` on frontier base.

Run `pytest engine/tests/labs/test_preset_catalog.py` after edits.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/labs/presets` | Paginated catalog (`category`, `tag`, `q`, `featured_only`, `offset`, `limit`) |
| GET | `/labs/presets/{id}` | Detail + `override_schema` for UI sliders |
| POST | `/labs/start` | Body: `{ preset_id, seed?, overrides?, world_name? }` |
| POST | `/labs/exit` | Reset to campaign scenario (default `frontier`) |

## Web routes

| Route | Role |
|-------|------|
| `/` | Home — Play Frontier / Labs |
| `/play` | Campaign game shell |
| `/labs` | Preset catalog |
| `/labs/new?preset=` | Tuning + Start lab |
| `/labs/run` | Lab game shell |

Lab saves use slots under `saves/labs/` via `POST /persistence/save?slot=labs/...`.

## Runtime metadata

Active lab worlds set `scenario_state`: `lab_mode`, `lab_preset_id`, `lab_title`, `lab_category`, `lab_display_id`. The world DTO exposes `lab_mode`, `lab_preset_id`, etc. Tick logic uses the underlying `scenario_id` (`frontier` / `genesis` / `cartel` / …), not the lab display id.

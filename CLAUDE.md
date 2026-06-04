## Solo UI — Godot, not `web/`

**The active solo client is Godot** in `realm_client/`. It talks to the Python engine via the solo socket (`realm_solo.py`, port **9000**); FastAPI on **8000** is for dev/tools, not the ship UI.

**`web/` is archived** — legacy Phase 1 Next.js prototype. **Do not add or change gameplay UI in `web/`.** New map, panels, labs, and controls belong in `realm_client/` (GDScript). Engine logic stays in `engine/`.

## Build version system (Godot ↔ engine)

Solo Godot and the Python engine share **`realm_build.json`** at the repo root (`build_id`, `player_starting_cash_cents`). Do not hardcode build IDs in multiple files.

- **Edit manifest:** `realm_build.json` — bump `build_id` when Godot↔engine compatibility breaks
- **Engine:** `engine/realm/core/build_info.py` → `version_payload()`; used by `/version` in `solo_fast_routes.py` and `routes_world.py`
- **Godot:** `realm_client/autoloads/WorldState.gd` loads the manifest; `GameHome.gd` rejects mismatches
- **Tests:** `engine/tests/core/test_build_info.py`
- **Stale engine on :9000:** restart solo engine in Godot Settings or kill orphaned `realm_solo.py` / `python.exe`

Full rule: `.cursor/rules/realm-build-version.mdc`

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

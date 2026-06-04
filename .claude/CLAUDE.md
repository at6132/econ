# Solo UI — Godot, not `web/`

- **Ship UI:** `realm_client/` (Godot / GDScript) → solo socket **:9000**
- **`web/` is archived** (legacy Next.js). Do not build new UI there.

# Build version system (Godot ↔ engine)

Solo Godot and the Python engine share **`realm_build.json`** at the repo root. Do not hardcode `build_id` in multiple files.

- Bump `build_id` in `realm_build.json` when Godot↔engine compatibility breaks
- Engine: `engine/realm/core/build_info.py` → `version_payload()` (`/version` on HTTP + solo socket)
- Godot: `realm_client/autoloads/WorldState.gd`; verify in `GameHome.gd`
- Tests: `engine/tests/core/test_build_info.py`
- Full rule: `.cursor/rules/realm-build-version.mdc`

# graphify
- **graphify** (`.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.

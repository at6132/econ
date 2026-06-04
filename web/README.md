# `web/` — archived (do not build here)

> **Agents:** The solo UI is **Godot** in [`../realm_client/`](../realm_client/), not this folder. Do not add map panels, gameplay controls, or new features under `web/` unless Avi explicitly asks to maintain the legacy browser prototype.

This directory is the **Phase 1 Next.js** client — kept for reference and occasional comparison only. **It is not the ship target.**

## Where to work instead

| Concern | Location |
|--------|----------|
| Solo UI, map, HUD, Labs | `realm_client/` (GDScript) |
| Simulation, actions, API | `engine/realm/` |
| Solo play loop | Godot → `realm_solo.py` on port **9000** |
| Optional HTTP dev API | `uvicorn realm.api:app` on port **8000** |

See also: root `AGENTS.md`, `.cursor/rules/realm-project-context.mdc`, `realm_docs/20_REALM_SOLO_CLIENT_VISUAL_STYLE_PROFILE.md`.

---

## Legacy run instructions (archived prototype only)

```bash
npm install
npm run dev
```

Dev proxy: requests to `/api/engine/*` rewrite to `http://127.0.0.1:8000/*`, so start the engine first:

```bash
cd ../engine
python -m pip install -e .
uvicorn realm.api:app --reload --port 8000
```

# Realm

> A 2D, web-first economic civilization sim where every business, price, currency, and service is invented and run by players — or by AI agents that act like players when you're alone.

**Status:** Phase 1 solo prototype — engine checklist complete (playtest gate in `realm_docs/13_PHASED_TODO.md` still requires external sessions). Spec in `realm_docs/`; runnable shell: Python engine + Next.js map.
**Designer / builder:** Avi (Sheva Studios).
**Doc set version:** v1.0.

---

## The 1-pager pitch

You spawn into a world that is geographically real but economically empty. There are no pre-defined "iron mines" or "shipping companies." There are plots of land with physical properties — terrain, climate, coastal access, what's in the ground. There are players (or AI agents) who can claim plots, hire labor, move goods, and build businesses. **Everything else is invented as the game goes.**

Want to start a shipping company? Find a coastal plot, get a vessel, haul other players' goods. Want to start a tech company? Don't even need a plot — write a piece of code that solves a problem other players have, sell it as a subscription. Want to be a banker, farmer, speculator, surveyor, market-maker? Compose the same nine economic primitives — land, materials, labor, time/distance, capital, production, markets, contracts, code — into whatever business you can dream up.

There are no quests. There are no levels. There is no NPC offering you a sword. There is only the economy you and the other players build together — with all the cooperation, competition, scams, cartels, innovations, booms, and crashes that come with that.

The fantasy: **"I am a tycoon in a world where the economy is real."** Not numbers-go-up-because-you-clicked. Real economic decisions, real counterparties, real consequences.

---

## Two modes, one engine

- **Solo mode (v1, ship first).** You vs a world full of AI agents — Tier 1 behavioral, Tier 2 optimizing, Tier 3 LLM-driven named characters. Pausable, save/load, scenario-based. Solo is the **existence test** of the design — if a stranger doesn't enjoy 1 hour of solo, the design is broken.
- **Public persistent multiplayer (later).** Real humans, slow real-time (1 game-day = 1 real-hour), permanent reputation, never pauses.
- **Competitive seasons / closed cohorts** sit between the two — time-boxed, hand-curated, used for balance testing and marketing.

Mobile is a **companion, not a port** — Bloomberg-terminal-in-your-pocket for monitoring and quick actions, never the place you build a factory.

---

## How to navigate this repo

The full design lives in `realm_docs/`. Read in order; each builds on the previous.

| # | Doc | What it is |
|---|---|---|
| 00 | [`realm_docs/00_README.md`](realm_docs/00_README.md) | Overview + read order |
| 01 | [`realm_docs/01_VISION.md`](realm_docs/01_VISION.md) | The pitch and what we're not building |
| 02 | [`realm_docs/02_DESIGN_PILLARS.md`](realm_docs/02_DESIGN_PILLARS.md) | The 7 non-negotiable design principles |
| 03 | [`realm_docs/03_PRIMITIVES_SPEC.md`](realm_docs/03_PRIMITIVES_SPEC.md) | The 9 economic atoms — the heart of the engine |
| 04 | [`realm_docs/04_LAWS_OF_THE_UNIVERSE.md`](realm_docs/04_LAWS_OF_THE_UNIVERSE.md) | The 10 engine-enforced "physics" rules |
| 05 | [`realm_docs/05_GAME_MODES.md`](realm_docs/05_GAME_MODES.md) | Solo, public, competitive seasons |
| 06 | [`realm_docs/06_AI_AGENT_DESIGN.md`](realm_docs/06_AI_AGENT_DESIGN.md) | Tier 1 / 2 / 3 agents |
| 07 | [`realm_docs/07_USER_CODE_LAYER.md`](realm_docs/07_USER_CODE_LAYER.md) | Lua services / SaaS-in-the-game (Phase 4+) |
| 08 | [`realm_docs/08_FIRST_HOUR_SCRIPT.md`](realm_docs/08_FIRST_HOUR_SCRIPT.md) | Minute-by-minute new-player walkthrough |
| 09 | [`realm_docs/09_TECH_ARCHITECTURE.md`](realm_docs/09_TECH_ARCHITECTURE.md) | Stack, services, data model, scaling |
| 10 | [`realm_docs/10_UX_AND_2D_VISUAL_LANG.md`](realm_docs/10_UX_AND_2D_VISUAL_LANG.md) | The five core views, mobile flows |
| 11 | [`realm_docs/11_BOOTSTRAP_AND_SEEDING.md`](realm_docs/11_BOOTSTRAP_AND_SEEDING.md) | How to avoid the empty-economy problem |
| 12 | [`realm_docs/12_RISKS_AND_MITIGATIONS.md`](realm_docs/12_RISKS_AND_MITIGATIONS.md) | What can kill the project |
| 13 | [`realm_docs/13_PHASED_TODO.md`](realm_docs/13_PHASED_TODO.md) | **The build plan and phase test gates — operational doc** |
| 14 | [`realm_docs/14_CURSOR_PROMPT.md`](realm_docs/14_CURSOR_PROMPT.md) | Drop-in Cursor prompt with full context |
| 15 | [`realm_docs/15_GLOSSARY.md`](realm_docs/15_GLOSSARY.md) | Precise definitions — read when terms drift |

**Working tip:** open `01–04` first. They are the foundation. If anything in them feels wrong, fix it before writing engine code.

---

## v1 stack (solo mode)

- **Frontend:** Next.js + React + TypeScript (strict)
- **2D map:** plain HTML/CSS in Phase 1, Pixi.js from Phase 2
- **Charts:** Recharts
- **Simulation engine:** Python (with type hints everywhere)
- **API (when needed):** FastAPI (keeps the stack uniform with the sim)
- **Database (solo):** SQLite per save file
- **In-game scripting:** Lua (Phase 4+)
- **LLM agents:** Anthropic API (Tier 3, Phase 3+)
- **Mobile:** React Native + Expo (later phase)

Don't introduce new tech without justification. Don't propose Rust/Go for the simulation core in v1.

---

## Working with the AI agent (Cursor)

This repo ships with two always-on Cursor rules in `.cursor/rules/`:

- [`realm-project-context.mdc`](.cursor/rules/realm-project-context.mdc) — loads the 9 primitives, 7 pillars, 10 laws, the v1 stack, coding conventions, the proposal format for non-trivial work, and the "things never to do" list.
- [`git-incremental-commits.mdc`](.cursor/rules/git-incremental-commits.mdc) — small reviewable commits as work progresses, not one giant end-of-session blob.

Update the **Current phase** line in `realm-project-context.mdc` whenever you advance phases. That single line keeps the agent in scope.

---

## Where we are right now

Phase 0 (spec + worked businesses) is documented; **active build is Phase 1** per [`realm_docs/13_PHASED_TODO.md`](realm_docs/13_PHASED_TODO.md).

### Run the prototype shell

Terminal 1 — engine API:

```powershell
Set-Location c:\Users\avita\econ\engine
python -m pip install -e .
uvicorn realm.api:app --reload --port 8000
```

Terminal 2 — web client (proxies `/api/engine` → engine):

```powershell
Set-Location c:\Users\avita\econ\web
npm install
npm run dev
```

Open http://localhost:3000 — claim a plot, survey it, pick a recipe, advance ticks until the run completes and inventory updates. Next slices: movement, markets, agents, SQLite.

### Phase 1 checklist (excerpt)

- [x] Tick-based time + deterministic RNG
- [x] Small grid world + terrain + hidden subsurface (API hides until surveyed)
- [x] Capital ledger + conservation tests; matter inventory + transfer test
- [x] Basic Next.js map + FastAPI bridge
- [x] Production recipes (5 templates) + tick-based completion + starter inventory
- [ ] Movement / transit
- [ ] Order books + P2P, contracts stub, reputation stub
- [ ] Tier 1 agents (~6), SQLite save/load

---

## A note on scope

This is a 5-to-10-year project at full scope. **Don't try to build the full vision in v1.** The phase plan in [`realm_docs/13_PHASED_TODO.md`](realm_docs/13_PHASED_TODO.md) is structured so each phase produces a shippable, testable, possibly sellable artifact. Build the phases in order. Don't skip the phase test gates — they exist because skipping them is how projects like this die.

The single biggest risk is *building too much before validating the design*. The phase gates exist specifically to protect against that.

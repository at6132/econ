# REALM — The Full Design & Build Spec

> Working title: **Realm** (placeholder — feel free to rebrand)
>
> A 2D, web-first, mobile-companion economic civilization sim where every business, price, currency, and service is invented and run by players (or AI agents in solo mode).

---

## What this doc set is

This is the complete planning bundle for the game we've been designing. Read in order — each doc builds on the previous one. **You should not start coding until you've at least skimmed docs 01–04.**

---

## Read order

| # | File | What it is | Why it matters |
|---|------|------------|----------------|
| 01 | `01_VISION.md` | The pitch, fantasy, what we're building, what we're not | Your north star. Re-read whenever you're tempted to feature-creep. |
| 02 | `02_DESIGN_PILLARS.md` | The 7 non-negotiable design principles | Use these as a filter for every feature decision. |
| 03 | `03_PRIMITIVES_SPEC.md` | The economic atoms — land, capital, labor, code, contracts, etc. | The actual technical heart of the game. Get these right and the game writes itself. |
| 04 | `04_LAWS_OF_THE_UNIVERSE.md` | The "physics" — conservation, time, decay, energy, info cost | What makes scarcity real and the economy stable. |
| 05 | `05_GAME_MODES.md` | Solo, public seed, competitive seasons, custom servers | Three products from one engine. |
| 06 | `06_AI_AGENT_DESIGN.md` | How NPCs work in solo mode (Tier 1/2/3 agents) | Solo mode is your existence test — this doc gates that. |
| 07 | `07_USER_CODE_LAYER.md` | The programmable services / SaaS-in-the-game system | The unlock that makes Realm different from every other sim. |
| 08 | `08_FIRST_HOUR_SCRIPT.md` | Minute-by-minute walkthrough of a new player's first hour | If this isn't fun on paper, the game isn't ready to build. |
| 09 | `09_TECH_ARCHITECTURE.md` | Stack, services, data model, scaling plan | How the thing actually gets built. |
| 10 | `10_UX_AND_2D_VISUAL_LANG.md` | 2D game shell, five core views, Frontier layout, mobile companion | What players actually see. |
| 11 | `11_BOOTSTRAP_AND_SEEDING.md` | How to avoid the empty-economy problem at launch | A specific risk that has killed every game like this. |
| 12 | `12_RISKS_AND_MITIGATIONS.md` | Honest list of what can kill this project and what to do about it | Re-read every quarter. |
| 13 | `13_PHASED_TODO.md` | **The build plan with phases, checklists, and per-phase test gates** | Your operational doc. This is what you work from day-to-day. |
| 14 | `14_CURSOR_PROMPT.md` | **Drop-in prompt for Cursor that loads it with full project context** | Paste at the start of any Cursor session. |
| 15 | `15_GLOSSARY.md` | Terminology so you don't drift on definitions | Use this to keep the spec coherent over months. |
| 16 | `16_VISION_ANCHOR_AND_PHASE_STATUS.md` | **North-star summary + where the repo is vs Phase 1** | Re-read when implementation starts to “lose the plot.” |
| 17 | `17_PHASE_1_COMPLETION_CHECKLIST.md` | **Phase 1 checklist (closed):** engine, API, UI, tests | Historical record; Phase 1 engineering complete. |
| 18 | `18_PHASE_2_COMPLETION_CHECKLIST.md` | **Phase 2 checklist:** Pixi, schematic, Tier 2, decay, intel, scenarios, polish | Active build tracker for Solo Polish & Visual Identity. |

---

## How to actually use these docs

1. **Read 01–04 today.** Internalize vision, pillars, primitives, laws. If anything feels wrong, fix it now — these are foundation.
2. **Read 08 (First Hour).** This is your gut-check on whether the design is fun.
3. **Read 13 (Phased TODO).** This is your roadmap. Phase 1 should start within 2 weeks of finishing the spec.
4. **Open 14 (Cursor Prompt) in Cursor.** Paste it as system context. Now Cursor has the full project loaded.
5. **Work the phased TODO.** Don't skip phase test gates. They exist because skipping them kills projects like this.

---

## Project metadata

- **Designer/Builder:** Avi (Sheva Studios)
- **Doc set version:** v1.0 (initial drop)
- **Last updated:** May 2026
- **Status:** **Phase 1 — Solo Engine Prototype in development** (see `16_VISION_ANCHOR_AND_PHASE_STATUS.md` for vision anchor vs phased roadmap). Spec + code both exist; Phase 1 **playtest gate** in doc 13 is not treated as passed until run deliberately.

---

## A note on scope

This is a 5–10 year project at full scope. **Do not try to build the full vision in v1.** The phased TODO (doc 13) is structured so each phase produces a shippable, testable, possibly even sellable artifact. If you build the way the TODO is laid out, you will have a real game in players' hands within ~12 months — not the full vision, but a real, fun, playable thing that proves the rest is worth building.

The single biggest risk to this project is *building too much before validating the design*. The phase gates in doc 13 exist specifically to protect against that.

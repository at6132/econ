# 20 — Realm solo client visual style profile (web + Godot)

> **Purpose:** Single source of truth for **look, palette, typography, and UI grammar** for the Realm **solo command deck** — whether implemented in **Next.js / CSS** (`web/`) or **Godot** (`realm-client/`).  
> **Companion docs:** `10_UX_AND_2D_VISUAL_LANG.md` (layout + product intent); this file is the **pixel-level spec** agents should follow.

---

## Godot note for implementers

Yes — Godot work here means **GDScript**, **Control**-based UI, **`Theme` resources**, **`StyleBoxFlat`**, fonts, and (for the map) **CanvasItem drawing**, **meshes**, or **shaders** — not a separate “game UI” aesthetic. Match this document; do not invent a cleaner Material-style skin unless Avi explicitly changes direction.

---

## One-sentence north star

**Late‑90s / early‑00s browser strategy sim meets tactical RPG menus:** a **dark, high-contrast command deck** around a **readable 2D world**, **text-first**, **dense data**, **chunky black borders**, **gold + cyan accents**, **monospace / bitmap-flavored type** — serious economy, not a consumer finance app.

---

## Canonical color tokens (copy these exactly)

These are the **authoritative hex values** from `web/app/globals.css` (`:root`). Godot should define the same constants (e.g. `RealmColors` autoload or a `Theme` color override table).

| Token | Hex | Role |
|------|-----|------|
| `realm-bg` | `#0c0612` | Page / app root background |
| `realm-bg2` | `#160a22` | Secondary void / gradients |
| `realm-panel` | `#241a36` | Panel surfaces (top of gradients) |
| `realm-panel-deep` | `#140c1f` | Panel depth (bottom of gradients) |
| `realm-border` | `#3d2f55` | Default structural border (purple-grey) |
| `realm-border-lit` | `#6b5a8a` | Hover / emphasis border |
| `realm-text` | `#f4ead8` | Primary body copy (warm paper) |
| `realm-dim` | `#c9b8a8` | Secondary lines, descriptions |
| `realm-muted` | `#8a7a98` | Labels, section kicker, de-emphasized UI |
| `realm-accent` | `#ffd84a` | **Gold:** brand, active tabs, titles, selection chrome |
| `realm-accent-dim` | `#c9a227` | Gold shadow / inset ring companion |
| `realm-magic` | `#6ee7ff` | **Cyan:** live numbers (tick, seed, cash), HUD facts, focus rings |
| `realm-warn` | `#ffb44a` | Warnings |
| `realm-danger` | `#ff6b6b` | Errors / destructive |
| `realm-ok` | `#7bed9f` | Success / live lane |

**Frequent hard-coded companions in CSS (keep aligned in Godot):**

- **Pure black frames:** `#000000` — outer borders, separators, “chunky” box shadows.
- **Chip inactive fill:** `#2a1f3d`
- **Chip active / “on” fill:** `#3d2d1a` (warm brown behind gold text)
- **Top strip gradient endpoints:** `#1e1530` → `#0c0612`
- **Pills / compact HUD wells:** `#1a1225`
- **Inset fields / logs:** `#120a1a`, `#0c0812`
- **Primary button text on gold:** `#1a0f08`

**Semantic usage (do not freestyle):**

- **Gold** = navigation state, panel titles, “this is the game shell speaking.”
- **Cyan** = **quantities and live state** (money, tick, seed, key metrics).
- **Muted purple-grey** = taxonomy and structure (group labels, table headers).
- **Warm paper** = reading content; reserve **pure white** flashes for rare emphasis only.

---

## Typography

| Role | Web implementation | Godot equivalent |
|------|---------------------|------------------|
| **Display / micro labels** | `"Press Start 2P"` — tiny caps, wide letter-spacing | Import the same font; use **all caps**; tight line-height; sizes ~6–11 px equivalent at 1080p reference |
| **UI body / buttons / lists** | `"VT323"` — readable monospace-adjacent | Same font family; base **~18–20 px** equivalent for dense panels |
| **Numbers** | `font-variant-numeric: tabular-nums` where possible | Monospace digits; align columns for inventory and markets |

**Case rules:**

- **ALL CAPS** for nav group labels (`FIELD OPS`, `COMMERCE`, `REALM`), map toolbar titles, and small-caps kickers.
- **Sentence case** for long help, inventory names, and footnotes — still in the same font stack.

---

## Atmosphere (CRT / deck — subtle)

From `globals.css` — the solo shell is not flat “enterprise dark mode”:

- **Global scanlines** on the viewport: very low opacity horizontal lines over everything.
- **Vignette** on the viewport edge: darkens corners; keeps eyes center-left on the map.
- **Behind the map only:** slow **sky gradient**, **aurora sweep**, **sparse stars** — all **pointer-events none**, **subdued** (`prefers-reduced-motion` must disable motion).

Godot: implement as **CanvasLayer** tints or **fullscreen ColorRect** shaders; **never** steal focus from controls; keep opacity in the same ballpark as the web CSS (roughly **0.06–0.2** for overlays).

---

## Layout grammar (Frontier solo)

Matches the shipped **Next.js** shell and the screenshot reference:

1. **Full viewport** — no centered “card” layout; the app is **edge-to-edge**.
2. **Top strip** — brand + subtitle left; **stat pills** and global actions right (tick / seed / cash, run controls, briefing).
3. **Second row** — **grouped tab chips** under small display-font group headers.
4. **Main row** — **map stage ~70%** (flex growth), **command panel ~min(400px, 100%)** fixed width on desktop; stacks below on narrow viewports.
5. **Map footnote** — one muted line at the bottom of the map (controls + legend hints).

---

## Control & panel styling rules

- **Corners:** default is **square** or **2px max** — never large border radii.
- **Borders:** **2–3 px** `#000` outer frames on panels, buttons, chips, modals. Inner accents use `realm-border` or dashed separators for “instrument” feel.
- **Shadows:** **offset hard shadows** (e.g. `3px 3px 0 #000`) on interactive tiles — this is part of the identity, not optional decoration.
- **Active chip / tab:** warm brown fill `#3d2d1a`, **gold text** `realm-accent`, optional **1 px inset** `realm-accent-dim`.
- **Inactive chip:** `#2a1f3d` fill, `realm-dim` text, black border.
- **Modals / command palette / settings:** gradient `165deg, #2a1f42 → #12081f`, black border, optional **double ring** (black + `realm-border-lit` or `realm-accent-dim`).

**Icon policy:** **Text-first.** Do not introduce icon packs or emoji-heavy chrome; glyphs are rare and functional (map legend only).

---

## Map rendering identity

- **Geometry:** **Organic triangular mesh** (jittered Delaunay-style regions), **not** a square city grid — reads as landmass, not spreadsheet cells.
- **Region stroke:** default dark edge `rgba(0,0,0,0.38)` ~1 px; **selected** = thick `realm-accent` gold stroke + slight glow.
- **Ownership:** player-owned unselected plots get a **cyan** hint stroke `rgba(110,231,255,0.5)` (same hue family as `realm-magic`).
- **Production badge fill (SVG reference):** `#7dd3fc` with black stroke.
- **World drop shadow:** subtle **downward** shadow on the mesh (`drop-shadow(0 2px 0 rgba(0,0,0,0.45))` in CSS) — Godot: duplicate mesh offset or shader.

**Map chrome:** floating toolbar bottom-right, **TERRAIN** label in display font, same chip styling as the nav row.

---

## Data density & tone

- **Prefer information** over whitespace; **tight padding** (8–14 px regions) is correct.
- **Tables** for inventories and markets: thin row dividers, **no zebra fadings**.
- **No glassmorphism**, no neon cyberpunk gradients on text, no rounded “iOS cards.”

---

## Accessibility & motion

- Maintain **WCAG-aware contrast** on text pairs; if a Godot theme tweak lowers contrast, fix it.
- **Respect reduced motion:** disable sky / twinkle / map breathe animations.

---

## Reference capture

A **screenshot of the current Frontier solo UI** (canonical target) is kept in the workspace for artists and agents:

`assets/c__Users_Avi_AppData_Roaming_Cursor_User_workspaceStorage_a25f39ab32aae36930e917243eceb368_images_image-60ddb9e7-f0ce-4fa6-8129-f6b9fbd5e2e3.png`

When in doubt, **open the web client** (`web/`, `npm run dev`) and **match it** before diverging in Godot.

---

## Checklist for new Godot UI

- [ ] Colors match the table above (no ad-hoc purple/teal palettes).
- [ ] Press Start 2P + VT323 (or documented alternatives Avi approves).
- [ ] Black 2–3 px frames + hard offset shadows on primary interactive surfaces.
- [ ] Gold for shell emphasis; cyan for live numeric state.
- [ ] Full-viewport layout; map dominant; panels peripheral.
- [ ] Scanline + vignette present but subtle; animations skippable.
- [ ] Map stays **triangular organic mesh** with gold selection language.

---

## File anchors in this repo

| Area | File |
|------|------|
| CSS tokens + component rules | `web/app/globals.css` |
| Godot project (target client) | `realm-client/` |
| Product-level UX intent | `realm_docs/10_UX_AND_2D_VISUAL_LANG.md` |

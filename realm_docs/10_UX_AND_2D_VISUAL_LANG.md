# 10 — UX and 2D Visual Language

> Realm is 2D forever. The job is to make **a serious economy legible inside a game shell** — the map and world read as a *place*, while markets, contracts, and production stay dense and honest. No 3D walkable dioramas; yes to chunky retro chrome, overlays, and screens full of real numbers.

---

## The visual concept

**North star:** late‑90s / early‑00s **strategy and browser sim** — full-viewport **world stage**, menus and command panels as **frames and pop-overs**, not a single spreadsheet canvas. Think **OGame / Travian / Civ-style map ownership** plus **RPG command menus** and **sim depth**, not a bank terminal skin.

Aesthetic reference points:
- **OGame / Travian / tribal conquest sims** — map as the emotional center; chrome around it
- **Factorio map view** — schematic clarity for production (later: plot schematic mode)
- **Classic RPG / tactics menus** — framed panels, readable hierarchy, keyboard-friendly lists
- **Dwarf Fortress maps** — abstract tiles that encode real state
- **Disco Elysium-style panels** — text-rich contracts and events when we need atmosphere
- **Order books and charts** — still present where they matter, but **framed as in-world instruments** (bazaar tape, ledger), not a wholesale copy of retail broker apps

Realm is a **command deck around a world**, not a floating 3D scene. Players live in **map + panels**: the middle stays geographic; commerce, logistics, and pacts open as **slides, tabs, or overlays**.

**Color language:** dark, high contrast. Terrain and status are color-coded (ownership, alerts, profit/loss). Accent color (gold / cyan) sells the “game HUD” without hiding data.

**Typography:** **Pixel or bitmap-flavored UI faces** for the shell (e.g. bitmap monospace / game fonts); numbers stay tabular and scannable. Readability beats novelty — avoid decorative fonts for long copy.

---

## Solo prototype (Frontier) — canonical layout

The **Next.js Frontier client** is the first expression of this language:

- **Full-viewport** shell; **no max-width “dashboard card.”**
- **Top strip:** brand, tick / seed / cash, primary actions (e.g. end turn), briefing.
- **Second row:** grouped **menu chips** (field ops, commerce, realm) — deep navigation without stealing map space.
- **Center:** **World stage** — animated atmosphere (sky / aurora / light) **behind** the map; **terrain grid** scales with viewport; tick feedback via subtle full-map flash.
- **Command panel:** **slide-in sheet** from the right (or stacked sheet on narrow viewports) for plot detail, market, logistics, contracts, log, atlas/roadmap.
- **Atlas:** explicit **live / stub / planned** feature map — honesty about what the engine does.

Later clients (Pixi map, multiplayer) should **preserve** this hierarchy: **world dominant**, **tools peripheral**, **density preserved**.

---

## The five core views

### 1. World Map View

What you see when you zoom out. The whole continent / globe.

**Shows:**
- Terrain colored by type
- Plot boundaries
- Plot ownership (color-coded by owner)
- Major settlements / population centers
- Active trade routes (lines with thickness = volume)
- Hot regions (price disturbances, breaking news)

**Interactions:**
- Click any plot → see public info, owner
- Hover any plot → quick stats tooltip
- Filter overlays: "show me where copper is being produced," "show me unowned plots," "show me current commodity prices by region"

**Visual reference:** Civilization-style **strategic map** as the default emotional anchor — 2D, trading- and production-aware.

### 2. Plot View

What you see when you zoom into your own plot.

**Two sub-modes:**

**a) Schematic (default for empire managers):**
A flowchart of your operations. Boxes = production units, arrows = material flow, numbers = throughput, sub-icons = labor / energy / inputs / outputs. Editable by drag-drop.

**b) Tile (optional for "I want to see my warehouse"):**
A small Factorio-style tile view of your plot's physical layout. Pretty but not the focus.

**Most players will live in schematic mode.** It communicates the actual important info.

### 3. Market View

Where order books, prices, charts, and your positions live — **presented as a bazaar / ledger screen** inside the same shell (tabs or overlays), not a separate “finance app” identity.

**Layout (conceptual):**
- Asset selector (commodity, equity, currency)
- Order book (bids and asks, depth) + chart + your open interest
- Trade history

**This is still where heavy market players camp** — but the **frame** stays game-native (borders, panels, optional CRT/light scanline restraint), not a clone of a retail broker UI.

### 4. Business / Contract View

Your books. Your active contracts. Your customers and suppliers.

- Income statement (last N days)
- Balance sheet
- Active contracts table
- Outgoing / incoming proposals
- Reputation summary

**Tone:** ledgers and charters — dense tables are fine; **wrap them in the same RPG/strategy panel chrome** as the rest of the UI.

### 5. Communications View

Messages, news, events.

- Inbox: messages from other players and AI agents
- News feed: market events, public announcements, world events
- Notifications log

---

## Cross-cutting UI elements

### Top bar
Always visible: clock (game-time + real-time), cash balance, net worth, current alerts, **primary world actions** (e.g. advance time when the design uses manual turns).

### Menu strip / dock
Grouped launchers for map-adjacent workflows (territory, commerce, realm systems). Prefer **one-click depth** over burying everything in a hamburger.

### Command palette (later)
Cmd-K fuzzy search remains a power-user affordance: "go to copper market," "show my contracts," etc.

### Notifications
Subtle. Bottom-right toaster for non-urgent. Full alert dialog for time-critical (contract about to expire, large price move, urgent message from rival).

### Command panel / overlays
Detail work happens in **sliding panels, modals, or docked sheets** that **do not shrink the world to a postage stamp** — the map stays the psychological “main screen” where possible.

---

## Mobile companion UX

Designed around five flows. Each must complete in <30 seconds.

### Flow 1: Market check
- Open app
- See top movers across the markets you watch
- Tap a market → quick chart + order book
- Place a quick limit order

### Flow 2: Contract proposal handling
- Push notification: "Margaux proposed a contract"
- Tap → see contract terms summary
- Accept / Reject / Counter (3 buttons)
- If counter: simple parameter editor (price, quantity, duration)

### Flow 3: Alert response
- Push: "Your stockpile of iron is low"
- Tap → see inventory + suggested actions
- One-tap: "Place reorder at market price"

### Flow 4: Quick check-in
- Open app
- See dashboard: net worth chart, last 24h, key events
- Read recent messages
- Close app

### Flow 5: Approve / authorize
- Push: "Service X is requesting permission to place orders on your behalf"
- Tap → see scope of permission
- Approve / Deny

**What's NOT on mobile:**
- Building / construction
- Code editing
- Plot management beyond viewing
- Long-form contract negotiation
- Anything that needs more than 30 seconds of focus

---

## UI design principles

### 1. Information density over decoration
Show more data than a casual mobile game. Players read **numbers and relationships**; decoration supports legibility, not fantasy tourism.

### 2. Real-time feels alive
Subtle animation on changes (prices, ticks, production complete). **Tick / turn feedback** on the map (flash, ripple, or icon pulse) reinforces that the world moved.

### 3. Every number is a hyperlink
A price → market. A player name → profile. A contract ID → contract. Connect the graph.

### 4. Keyboard shortcuts everywhere
Power users live in shortcuts. Discoverable via command palette and tooltips.

### 5. Customizable layouts
Players can resize panels, dock them, save layouts. (Defer fully customizable layouts to v2 if needed; v1 ships with sensible defaults.)

### 6. Always show consequences
Before every action: cost, effect, expected outcome. No surprises.

### 7. Failure should be informative
Rejections explain *why* so players learn.

---

## What the game is NOT going to look like

- Not a **3D walkable** factory or city (no first-person management)
- Not **generic mobile tycoon** pastel UI that hides the economy
- Not **isometric dollhouse** as the primary metaphor (Factorio-style *schematic* inside a plot is fine)
- Not **CK-style portrait theater** as the main screen

**Allowed and encouraged:** intentional **2D tile maps**, **retro / pixel HUD chrome**, **full-screen world stage**, **stacked menus** — as long as **conservation and clarity** stay king.

---

## A note on accessibility

Dense UIs need care:
- Color is *never the only* indicator (icon + color, not just color)
- Text is resizable
- Keyboard-only navigation works everywhere
- Screen-reader compatible labels
- High-contrast mode
- Configurable tick rate / pause for cognitive load
- Respect **`prefers-reduced-motion`** for atmospheric animations

---

## Build order

- **Phase 1:** functional loop + **Frontier** shell (HTML/CSS map stage, command panel, honest atlas). Tables and actions first.
- **Phase 2:** Pixi.js map where needed; charts via Recharts; strengthen motion and feedback.
- **Phase 3:** polish, layout saves, richer atmosphere (within performance budgets).
- **Mobile:** parallel track once Phase 2 is done.

Don't waste polish on UI before the mechanics are validated. **A beautiful shell on a broken economy is wasted work.**

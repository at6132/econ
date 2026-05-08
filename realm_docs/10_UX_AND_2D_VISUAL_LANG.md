# 10 — UX and 2D Visual Language

> Realm is 2D forever. The visual job is to communicate dense economic information legibly, not to be cinematic. Real traders use Bloomberg terminals, not 3D dioramas. Lean into that.

---

## The visual concept

Aesthetic reference points:
- **Bloomberg terminals** — dense, dark, information-rich
- **Factorio map view** — schematic 2D of complex production
- **OGame / Travian** — old-school browser sims with clear plot grids
- **Dwarf Fortress maps** — abstract symbols communicating real meaning
- **Modern stock-trading apps** (Robinhood, IBKR) — clean charts and order books
- **Disco Elysium-style UI** for messages and contracts — text-rich, atmospheric

Realm is a **workspace, not a scene.** Players have multiple panels open. They arrange their UI like a trader arranges monitors.

**Color language:** dark mode default. High contrast. Color-coded everything (terrain, asset categories, profit/loss, alerts).

**Typography:** monospace for numbers, sans-serif for text. Real-world finance UI conventions.

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

**Visual reference:** Imagine Civilization V's strategic view, but 2D and trading-focused.

### 2. Plot View

What you see when you zoom into your own plot.

**Two sub-modes:**

**a) Schematic (default for empire managers):**
A flowchart of your operations. Boxes = production units, arrows = material flow, numbers = throughput, sub-icons = labor / energy / inputs / outputs. Editable by drag-drop.

**b) Tile (optional for "I want to see my warehouse"):**
A small Factorio-style tile view of your plot's physical layout. Pretty but not the focus.

**Most players will live in schematic mode.** It communicates the actual important info.

### 3. Market View

The trader's home. Where order books, prices, charts, and your portfolio live.

**Layout:**
- Top: asset selector (commodity, equity, currency)
- Left: order book (bids and asks, depth)
- Center: price chart (candlesticks + volume)
- Right: your position in this asset, your open orders, related news
- Bottom: trade history

**This is the screen players will spend the most time on.** It needs to feel like a real trading platform.

### 4. Business / Contract View

Your books. Your active contracts. Your customers and suppliers.

- Income statement (last N days)
- Balance sheet
- Active contracts table
- Outgoing / incoming proposals
- Reputation summary

Sober, spreadsheet-y, dense. This is the CEO's desk.

### 5. Communications View

Messages, news, events.

- Inbox: messages from other players and AI agents
- News feed: market events, public announcements, world events
- Notifications log

---

## Cross-cutting UI elements

### Top bar
Always visible: clock (game-time + real-time), cash balance, net worth, current alerts.

### Side dock
Quick-launchers for each of the five views. One click to swap.

### Command palette
Cmd-K opens a fuzzy search: "go to copper market," "send message to Margaux," "show my contracts," "place order for iron." Power-user feature, but reveals the depth of the system.

### Notifications
Subtle. Bottom-right toaster for non-urgent. Full alert dialog for time-critical (contract about to expire, large price move, urgent message from rival).

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
Show 5x more data than a typical game UI. Players will be looking at numbers, not characters.

### 2. Real-time feels alive
Subtle animation on changes (a price flickering green/red on update). Avoids flashing chaos but communicates that the world is moving.

### 3. Every number is a hyperlink
A price → click to open market. A player name → click to open profile. A contract ID → click to open contract. Connect the graph.

### 4. Keyboard shortcuts everywhere
Power users will live in shortcuts. Discoverable via the command palette and hover-tooltips.

### 5. Customizable layouts
Players can resize panels, dock them, save layouts. (Defer fully customizable layouts to v2 if needed; v1 ships with sensible defaults.)

### 6. Always show consequences
Before every action, show: "If you do this, here's what happens. Here's the cost. Here's the expected outcome." No surprises.

### 7. Failure should be informative
If an action is rejected, say *why*. "Insufficient capital." "Plot does not have a harbor." "Counterparty's reputation is below your minimum threshold." Players learn from rejection.

---

## What the game is NOT going to look like

- Not a 3D walkable world
- Not Stardew Valley's pretty pixel art
- Not RuneScape's medieval avatars
- Not isometric tycoon (Tycoon games like Two-Point Hospital)
- Not Crusader Kings' portrait-driven UI

If a designer ever pitches "wouldn't it be cool if you could walk around your factory in 3D" — politely decline. The visual language is screens-of-information, not scenes.

---

## A note on accessibility

A trading-style UI is inherently dense. Accessibility matters:
- Color is *never the only* indicator (icon + color, not just color)
- Text is resizable
- Keyboard-only navigation works everywhere
- Screen-reader compatible labels
- High-contrast mode
- Configurable tick rate / pause for cognitive load

---

## Build order

- **Phase 1:** ugly, functional UIs. Tables. Buttons. No styling. Get the loop working.
- **Phase 2:** apply the visual language. Pixi.js for the world map. Charts via Recharts.
- **Phase 3:** polish. Animation. Custom layouts.
- **Mobile:** parallel track once Phase 2 is done.

Don't waste polish on UI before the mechanics are validated. **A beautiful UI on a broken game is wasted work.**

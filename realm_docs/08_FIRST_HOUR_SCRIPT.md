# 08 — First Hour Script

> If this isn't fun on paper, the game isn't ready to build. The first hour determines whether a player ever returns. Walk through this scene-by-scene before any code is written.

---

## The setup

This walkthrough describes a new player's *first solo-mode session in v1.* No multiplayer, no user-code yet, no fancy graphics. Just: can the core economic loop captivate a stranger for 60 minutes?

Scenario: **"Frontier."** Empty continent, you and 8 AI rivals, similar starting resources.

---

## Minute 0 — Title screen

Player launches the game. Sees:
- **Title:** REALM
- Three buttons: **New Game**, **Continue**, **Tutorial**

They click **New Game**.

## Minute 0–2 — World generation

Cinematic but quick:
- World map slowly fills in: continents, oceans, terrain
- "Generating world..." → "Placing AI rivals..." → "Surveying initial conditions..."
- World finishes drawing: a 2D continent, hex-grid or square-grid, color-coded terrain.

A simple intro card:
> *"You are an entrepreneur arriving in a new world. There is no economy yet. Whatever exists, you and others will build."*

(Optional skip button for returning players.)

## Minute 2–5 — Plot selection

The player sees a globe (zoomable 2D map) with:
- **Available plots** highlighted (a few dozen)
- Each plot's *visible* properties on hover (terrain, climate, coastal y/n)
- *Subsurface composition is hidden.*

A small UI panel: **"Choose your starting plot. You can buy more later."**

The player picks one. Say they pick a coastal plain.

A confirmation: **"You now own Plot #017. Starting capital: $10,000."**

The world map zooms to their plot. They see a cleared rectangle with their character icon, surrounded by tutorial markers.

## Minute 5–10 — First decision: what do you actually do?

This is the critical moment. Many tycoon games fail here because the player has no idea what to do first.

**Our solution:** A simple guided onboarding that introduces *primitives*, not specific strategies. Three suggested starting paths:

> "You can do anything in Realm. To get started, here are three common first moves:
> 
> 1. **Survey your plot.** Find out what's underground. Maybe valuable, maybe nothing. Costs $500.
> 2. **Build extraction.** Without a survey, you can build a generic extraction operation if you suspect surface resources (forestry, fishing if coastal, etc).
> 3. **Skip extraction and trade instead.** Use your $10,000 to buy goods cheap and sell them where they're more expensive. There's a market screen for that.
>
> Every other path branches from these."

Player picks one. The guidance disappears after the first time. **The game is sandbox — these suggestions are just to overcome blank-page paralysis.**

Let's say they survey. The survey takes 1 game-day (which at 1x speed = ~10 real seconds in a paused-with-fast-time tutorial).

Result: *"Your plot has light copper deposits, moderate clay, and surface timber."*

## Minute 10–15 — First decision-with-consequence

The player now has information. They have $9,500 left. They have a coastal plot with copper, clay, and timber.

UI shows the **Market panel** — all current order books in the world.

They see:
- **Iron** — high price, no local supply. (Distant.)
- **Copper** — moderate price, two AI sellers, one buyer.
- **Timber** — low price, lots of supply.
- **Clay** — surprisingly high price, only one seller.

This is the moment of insight: *"Clay is selling high. I have clay. I should mine clay."*

They open the **build panel** for their plot. Options:
- Clay quarry: cost $3,000, requires labor, produces ~50 units/day.
- Sawmill: cost $1,500, processes timber.
- Fishing dock: cost $2,000, requires labor, produces fish.

They build a clay quarry. Cost $3,000. Construction takes 2 game-days (= ~20 real seconds at fast speed).

They also need labor. They open the **labor panel.** Wages in their region are $20/day per worker. They hire 5 workers.

## Minute 15–25 — First production cycle

The world ticks. Their quarry comes online. Workers begin extracting. Inventory shows 50 clay/day building up.

They open the market again. Place a sell order: 100 clay at the going rate.

A few minutes (or a few game-days) later: **"Order filled. +$1,200 to your account."**

The dopamine hit. *They just made money in a player-driven economy.*

## Minute 25–35 — First antagonist

A message appears: from one of the AI rivals.

> **"Margaux the Industrialist:** I see you've started clay production. I am also expanding into clay. I'd like to propose a 30-day exclusive supply contract — I will pay you $25/unit, above market, in exchange for first refusal on your output. Will you accept?"

This is a *contract* primitive in action. The player has a choice:

- **Accept.** Stable revenue. But locked in if market prices spike.
- **Reject.** Stay in the spot market. More upside, more volatility.
- **Counter-propose.** "I want $30/unit." Negotiation.

This is the moment Realm reveals what kind of game it is. **It's not just clicking buildings. It's making real economic decisions with real-feeling counterparties.**

Whatever the player does, they're now engaged. They've felt the shape of the game.

## Minute 35–45 — The wider world reveals itself

The player explores other UI panels:
- **News feed:** *"Rico the Speculator just bought 500 timber at market. Prices spiked 5%."* *"A new copper mine has opened in Region 4."*
- **Reputation panel:** Their own reputation is starting to accumulate.
- **Map view:** They can see other players' (AI) plots and what each is doing publicly.

They start to *understand* that other actors are doing things *because of their goals*, not because of scripted events. Margaux is buying clay because Margaux's strategy involves industrial production. Rico is speculating because that's his nature.

They build a second improvement on their plot — a sawmill, to also process timber. They hire more workers.

A second message arrives:

> **"Generic NPC laborer pool:** Wages have risen in your region by 10%. Three workers have left for higher pay elsewhere."

Cause and effect. They need to either pay more or accept reduced output.

## Minute 45–55 — A choice that locks in identity

By now they're profiting modestly. Their account has $8,000 (recovered from their initial spend). They have a few options:

- **Buy a second plot.** Horizontal expansion in their existing vertical.
- **Buy a vessel.** Move into shipping, transport their own goods.
- **Lease their plot to someone else and become a trader.** Pure financial play.
- **Take a loan** from the NPC bank to accelerate growth.

This is the point at which the player picks an *identity arc.* Not a class. An emergent identity. They are *deciding what kind of entrepreneur they're going to be.*

## Minute 55–60 — The hook

End of first hour. Game saves automatically. Player has:
- Established a small business
- Made $4,000 in net profit
- Negotiated their first contract
- Been antagonized by a named rival
- Felt the cause-and-effect of an economy
- Identified an arc to pursue

A summary card:
> *"Day 4 in Realm. Net worth: $14,200. Reputation: New."*
>
> *"Your decisions today affected the prices in three markets. Margaux is watching you. Rico has not noticed you yet. The world will keep going whether you play or not."*
>
> **"Continue?"** **"Save and quit?"**

If they save and quit, the world continues for AI agents (in solo mode this is configurable — default is the world pauses when you're away).

The hook is: *what happens next?* They have a stake. They want to know.

---

## What this walkthrough is testing

The first hour script is a thought experiment, not a UI spec. It's testing whether the *primitives produce a fun, comprehensible experience.* Specifically:

- Does the player ever feel lost?
- Does the player ever feel like nothing they do matters?
- Does the player ever feel like the game is on rails?
- Does the player feel friction (that's good) or confusion (that's bad)?
- Do the AI rivals feel like real opponents or like skinned scripted events?
- Is there a moment of insight? (When they realize clay is high and they have clay.)
- Is there a moment of decision-with-consequence? (Margaux's contract.)
- Is there a moment of identity formation? (Choosing the second move.)

If you can read this walkthrough and not feel "yes this would be fun," **the design isn't ready.** Iterate the primitives until the walkthrough reads as fun.

---

## What we are *not* doing in the first hour

- No combat.
- No quests with objectives.
- No 3D characters with dialogue trees.
- No skill trees or leveling.
- No tutorial pop-ups beyond the initial three suggestions.
- No "press X to continue" pacing.
- No fixed playtime — the player can stop anytime.

The fantasy is *adulthood, agency, and consequence*, not *guidance, progression, and reward.*

---

## How to validate this walkthrough

Once you have a Phase 1 prototype (see doc 13), get 3–5 strangers to play it for one hour. Watch them. Note:

- When are they confused?
- When do they smile?
- When do they zoom out and think?
- When do they get frustrated?
- When do they say "oh, interesting"?
- Do they want to keep playing at the end?

If 3 of 5 say "yes, let me play more," you have a game. If fewer, the design needs work — and it's better to find that out from a prototype than from a launch.

# 01 — Vision

## The one-sentence pitch

**Realm is a 2D web-based economic civilization sim where every business, every price, every currency, and every service is invented and run by players — or by AI agents that act like players when you're alone.**

## The longer pitch

You spawn into a world that is geographically real but economically empty. There are no pre-defined "iron mines" or "shipping companies." There are plots of land with physical properties — terrain, climate, coastal access, what's in the ground. There are players (or AI agents) who can claim plots, hire labor, move goods, and build businesses. Everything else is invented as the game goes.

Want to start a shipping company? Find a coastal plot, get a vessel, and start hauling other players' goods. Want to start a tech company? You don't even need a physical plot — write a piece of code that solves a problem other players have, and sell it as a subscription. Want to start a bank? Take deposits, issue loans, build trust. Want to be a farmer? Find arable land, grow crops, sell to the food-processing companies. Want to be a speculator? Trade the commodities, equities, and currencies that emerge from everyone else's economic activity.

There are no quests. There are no levels. There is no NPC offering you a sword. There is only the economy you and the other players (or AI agents) build together — with all the cooperation, competition, scams, cartels, innovations, booms, and crashes that come with that.

## The fantasy

The fantasy is **"I am a tycoon in a world where the economy is real."** Not "tycoon" in the sanitized sense of building 1000 hot dog stands and watching a number go up. Tycoon in the sense of *someone reading market reports at 6am, making a decision that affects 50 other people's livelihoods, and then watching the market move because of it.*

It's the fantasy of being a *node* in a real economic web. Of having reputation that matters. Of building something whose value is determined by what other intelligent agents will pay for it, not by a hidden game balance spreadsheet.

For different players the fantasy looks different:
- **The builder** wants to grow a business empire across multiple verticals.
- **The trader** wants to spot mispricings and arbitrage them.
- **The strategist** wants to dominate a vertical or corner a market.
- **The engineer** wants to build automated systems and SaaS that other players use.
- **The diplomat** wants to form alliances, run cartels, negotiate deals.
- **The storyteller** wants to be the named figure other players love or hate.

All of these are valid. All of these emerge from the same primitives.

## What Realm is not

- It is **not** a "tycoon" game in the Cookie Clicker / idle-money sense. Numbers don't go up because you click. They go up because you made a real economic decision that worked out.
- It is **not** a Civilization-style game with tech trees and victory conditions. There is no win state. There is only what you build and how long it lasts.
- It is **not** a designer-driven content game. We do not write quests. We do not script storylines. The story comes from what players do.
- It is **not** play-to-earn / blockchain / token speculation. The in-game economy is real *to the game.* It does not interact with crypto or fiat. (We may revisit later, but it is not the pitch.)
- It is **not** a clone of Eve Online. Eve is the closest reference but is space-fantasy combat-focused. Realm is economy-focused with no PvP combat in v1.
- It is **not** 3D. Realm is 2D forever. Pretty maps, dense data UIs, schematic plot views.

## The two modes (one engine, two products)

**Solo mode.** You vs the world. The world is full of AI agents (some basic, some LLM-driven and named) that act as your competitors, customers, suppliers, and rivals. Pausable, replayable, scenario-based. This is also where new players learn before risking anything in multiplayer. **Solo mode is the existence test of the design** — if it isn't fun, nothing built on top is fun either.

**Public mode.** Persistent shared world. Real other humans. Real consequences. Real reputation. Slow real-time. Markets never sleep. Most players will live here.

**Competitive seasons / closed-cohort betas.** Curated multiplayer scenarios — time-boxed, often with prizes or rankings. New players earn their way in via solo mode performance. Doubles as marketing engine and balance-testing arena.

## The platforms

- **Web (primary).** Where serious play happens. Building, programming, contracts, deep market analysis. Desktop-first UI.
- **Mobile companion (iOS + Android via React Native).** Bloomberg-terminal-in-your-pocket. Monitor markets, accept/reject offers, get alerts, execute quick trades, message contacts. **Not a full game client** — deliberately scoped to "managing your empire on the go."

## The end-state vision (5–10 years out)

A persistent online economy with:
- Tens of thousands of concurrent players across multiple shards
- Player-issued currencies and a foreign exchange market between them
- Player-built financial instruments (loans, bonds, derivatives, insurance)
- Player-built SaaS services consumed by other players (analytics, automation, logistics)
- Player-formed corporations with shareholders and governance
- Player-formed nations with taxation and regulation
- A solo-mode product that is itself a complete commercial game with millions of players
- A culture of streamers, analysts, and writers who follow the public economy like a real one
- Academic interest from economists who study Realm's emergent dynamics

That's the dream. It's at least 5 years away. **Doc 13 (Phased TODO) is how we get there in steps that each ship something real.**

## The strategic edge

Why does this work when so many ambitious sims have failed?

1. **Solo mode is shippable as a standalone game.** We don't need multiplayer to ship. We can validate the entire design with one player and AI agents. That's a vastly smaller risk than "build MMO from day one."
2. **The user-code layer is a moat.** Once players have built valuable services inside the game, they can't easily migrate to a competitor. The platform compounds.
3. **2D + emergent content = scalable content.** We don't have to write quests. The economy generates them.
4. **Mobile companion = retention.** Players check in throughout the day. The game is in their pocket, not just on their desktop.
5. **The fantasy is underserved.** There are dozens of clicker tycoon games and dozens of strategy games. There are very few "I am a real merchant in a real economy" games, and the few that exist (Eve, Patrician, Port Royale) are aging or dead.
